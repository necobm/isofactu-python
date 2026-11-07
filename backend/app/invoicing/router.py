"""HTTP endpoints of the Invoicing module.

Every endpoint requires a logged-in ADMIN (the tenant) and only touches that tenant's
data: the repositories are bound to the current user.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.deps import CurrentTenant
from app.accounts.models import User
from app.clients.models import Client
from app.clients.repository import ClientRepository
from app.core.database import get_session
from app.invoicing.invoice_state import InvoiceState
from app.invoicing.models import FiscalData, Invoice, InvoiceLine, Serial, Subject
from app.invoicing.repository import (
    FiscalDataRepository,
    InvoiceRepository,
    SerialRepository,
    SubjectRepository,
)
from app.invoicing.schemas import (
    FiscalDataRead,
    FiscalDataWrite,
    InvoiceCollection,
    InvoiceCreate,
    InvoiceRead,
    InvoiceUpdate,
    InvoiceWrite,
    SerialRead,
    SerialWrite,
)
from app.invoicing.value_objects import Address, IdentificationDocument, InvoiceNumber, Issuer

SessionDep = Annotated[AsyncSession, Depends(get_session)]
LimitParam = Annotated[int, Query(ge=1, le=200, description="Page size")]
OffsetParam = Annotated[int, Query(ge=0, description="Number of items to skip")]
StateParam = Annotated[
    InvoiceState | None, Query(description="Only invoices in this state (DRAFT | ISSUED)")
]
fiscal_data_router = APIRouter(prefix="/fiscal-data", tags=["Fiscal data"])
serial_router = APIRouter(prefix="/serial", tags=["Serials"])
invoice_router = APIRouter(prefix="/invoice", tags=["Invoices"])


# -- fiscal data ----------------------------------------------------------------------


@fiscal_data_router.get(
    "",
    response_model=FiscalDataRead | None,
    summary="Fiscal data of the account",
    description="The tenant's identity as invoice issuer, or `null` while it is not set up.",
)
async def get_fiscal_data(tenant: CurrentTenant, session: SessionDep) -> FiscalData | None:
    return await FiscalDataRepository(session, tenant.id).get()


@fiscal_data_router.put(
    "",
    response_model=FiscalDataRead,
    summary="Set the fiscal data of the account",
    description=(
        "Creates or replaces the fiscal data. It is stamped as issuer on every invoice saved "
        "from then on (drafts included when they are next saved); issued invoices keep the "
        "data they were issued with."
    ),
)
async def put_fiscal_data(
    tenant: CurrentTenant, payload: FiscalDataWrite, session: SessionDep
) -> FiscalData:
    repo = FiscalDataRepository(session, tenant.id)
    data = await repo.get()
    document = IdentificationDocument(**payload.document.model_dump())
    address = Address(**payload.address.model_dump())
    if data is None:
        data = await repo.add(
            FiscalData(
                owner=tenant, company_name=payload.company_name, document=document, address=address
            )
        )
    else:
        data.company_name = payload.company_name
        data.document = document
        data.address = address
    await session.commit()
    return data


# -- serials --------------------------------------------------------------------------


async def _serial_read(serial: Serial, repo: SerialRepository) -> SerialRead:
    issued, highest = (await repo.usage()).get(serial.id, (0, 0))
    return _serial_read_with(serial, issued, highest)


def _serial_read_with(serial: Serial, issued: int, highest: int) -> SerialRead:
    next_number = serial.initial_number if issued == 0 else max(highest + 1, serial.initial_number)
    return SerialRead.model_validate(
        {
            "id": serial.id,
            "prefix": serial.prefix,
            "suffix": serial.suffix,
            "initial_number": serial.initial_number,
            "start_date": serial.start_date,
            "end_date": serial.end_date,
            "issued_count": issued,
            "next_number": next_number,
        }
    )


async def _find_serial(serial_id: int, repo: SerialRepository) -> Serial:
    serial = await repo.find(serial_id)
    if serial is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Serial not found")
    return serial


async def _check_unique(
    payload: SerialWrite, repo: SerialRepository, current: Serial | None
) -> None:
    clash = await repo.find_by_parts(payload.prefix, payload.suffix)
    if clash is not None and clash is not current:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "A serial with the same prefix and suffix already exists"
        )


@serial_router.get(
    "",
    response_model=list[SerialRead],
    summary="List serials",
    description=(
        "The numbering series of the account, with how many invoices use each one and the "
        "number the next invoice issued with it would get."
    ),
)
async def list_serials(tenant: CurrentTenant, session: SessionDep) -> list[SerialRead]:
    repo = SerialRepository(session, tenant.id)
    usage = await repo.usage()
    return [_serial_read_with(s, *usage.get(s.id, (0, 0))) for s in await repo.find_all()]


@serial_router.post(
    "",
    response_model=SerialRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a serial",
    description="`409` when the account already has a serial with the same prefix and suffix.",
)
async def create_serial(
    tenant: CurrentTenant, payload: SerialWrite, session: SessionDep
) -> SerialRead:
    repo = SerialRepository(session, tenant.id)
    await _check_unique(payload, repo, None)
    serial = await repo.add(Serial(owner=tenant, **payload.model_dump()))
    await session.commit()
    return await _serial_read(serial, repo)


@serial_router.get("/{serial_id}", response_model=SerialRead, summary="Get a serial")
async def get_serial(tenant: CurrentTenant, serial_id: int, session: SessionDep) -> SerialRead:
    repo = SerialRepository(session, tenant.id)
    return await _serial_read(await _find_serial(serial_id, repo), repo)


@serial_router.put(
    "/{serial_id}",
    response_model=SerialRead,
    summary="Update a serial",
    description=(
        "Once an issued invoice uses the serial, its prefix, suffix and initial number are "
        "frozen (`409` when changed); the dates can still be edited, e.g. to close it."
    ),
)
async def update_serial(
    tenant: CurrentTenant, serial_id: int, payload: SerialWrite, session: SessionDep
) -> SerialRead:
    repo = SerialRepository(session, tenant.id)
    serial = await _find_serial(serial_id, repo)
    issued = await repo.issued_count(serial)
    frozen = (serial.prefix, serial.suffix, serial.initial_number)
    if issued and frozen != (payload.prefix, payload.suffix, payload.initial_number):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "The prefix, suffix and initial number of a serial in use cannot be changed",
        )
    await _check_unique(payload, repo, serial)
    for field, value in payload.model_dump().items():
        setattr(serial, field, value)
    await session.commit()
    return await _serial_read(serial, repo)


@serial_router.delete(
    "/{serial_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a serial",
    description=(
        "`409` when an issued invoice uses it (set an end date instead). Drafts that "
        "remembered the serial simply forget it."
    ),
)
async def delete_serial(tenant: CurrentTenant, serial_id: int, session: SessionDep) -> None:
    repo = SerialRepository(session, tenant.id)
    serial = await _find_serial(serial_id, repo)
    if await repo.issued_count(serial):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "A serial used by issued invoices cannot be deleted; set an end date to retire it",
        )
    await repo.delete(serial)
    await session.commit()


# -- invoices -------------------------------------------------------------------------


async def _current_issuer(session: AsyncSession, tenant: User) -> Issuer:
    """The issuer to stamp on an invoice being saved, or a 409 until the account has its
    fiscal data set up."""
    data = await FiscalDataRepository(session, tenant.id).get()
    if data is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Set up the fiscal data of the account before creating invoices",
        )
    return data.as_issuer()


# -- invoices -------------------------------------------------------------------------


@invoice_router.get(
    "",
    response_model=InvoiceCollection,
    summary="List invoices",
    description=(
        "Returns the collection of invoices stored in the database, newest first. "
        "Optionally restricted to a single state with `?state=`."
    ),
)
async def list_invoices(
    tenant: CurrentTenant,
    session: SessionDep,
    state: StateParam = None,
    limit: LimitParam = 50,
    offset: OffsetParam = 0,
) -> InvoiceCollection:
    repo = InvoiceRepository(session, tenant.id)
    items = await repo.find_all(state=state, limit=limit, offset=offset)
    total = await repo.count(state=state)
    return InvoiceCollection(
        items=[InvoiceRead.model_validate(i) for i in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@invoice_router.get("/{invoice_id}", response_model=InvoiceRead, summary="Get an invoice")
async def get_invoice(tenant: CurrentTenant, invoice_id: int, session: SessionDep) -> Invoice:
    invoice = await InvoiceRepository(session, tenant.id).find(invoice_id)
    if invoice is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
    return invoice


def _validation_error(field: str, message: str) -> HTTPException:
    return HTTPException(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        [{"loc": ["body", field], "msg": message, "type": "value_error"}],
    )


async def _find_client(client_id: int, session: AsyncSession, tenant: User) -> Client:
    """The client referenced by the payload, or a 422. Clients of other tenants count as
    missing."""
    client = await ClientRepository(session, tenant.id).find(client_id)
    if client is None:
        raise _validation_error("clientId", "Client not found")
    return client


def _copy_into(subject: Subject, client: Client) -> Subject:
    subject.full_name = client.full_name
    subject.document = client.document
    subject.address = client.address
    return subject


async def _recipient_from(client: Client, tenant: User) -> Subject:
    """The invoice's own copy of the client: no reference is kept to the client, so editing
    or deleting it later never changes the invoice."""
    return _copy_into(Subject(owner=tenant), client)


async def _refresh_recipient(
    invoice: Invoice, client: Client, session: AsyncSession, tenant: User
) -> None:
    """Point a draft at (a copy of) `client`. The existing copy is reused when this is the
    only invoice holding it; a copy shared with other invoices (legacy data) is left alone
    and a fresh one is made."""
    repo = SubjectRepository(session, tenant.id)
    if await repo.reference_count(invoice.recipient) == 1:
        _copy_into(invoice.recipient, client)
    else:
        invoice.recipient = await _recipient_from(client, tenant)


async def _resolve_number(
    payload: InvoiceWrite, session: AsyncSession, tenant: User, repo: InvoiceRepository
) -> tuple[Serial | None, InvoiceNumber]:
    """The serial referenced by the payload and the number to store: drafts stay
    numberless (the serial, if any, is just remembered); issuing takes the next number of
    the serial, which must exist and be available on the issue date."""
    serial = None
    if payload.serial_id is not None:
        serial = await SerialRepository(session, tenant.id).find(payload.serial_id)
        if serial is None:
            raise _validation_error("serialId", "Serial not found")
    if payload.state is InvoiceState.DRAFT:
        return serial, InvoiceNumber()
    if serial is None:
        raise _validation_error("serialId", "A serial is required to issue an invoice")
    if not serial.is_available_on(payload.issue_date):
        raise _validation_error("serialId", "The serial is not available on the issue date")
    return serial, serial.number(await repo.next_number(serial))


@invoice_router.post(
    "",
    response_model=InvoiceRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an invoice",
    description=(
        "Creates a DRAFT (numberless) or an ISSUED invoice whose recipient is a copy of the "
        "client `clientId`. When issuing, the next number of the serial `serialId` is "
        "assigned (the serial must be available on the issue date). The issuer is the fiscal "
        "data of the account (`409` until it is set up)."
    ),
)
async def create_invoice(
    tenant: CurrentTenant, payload: InvoiceCreate, session: SessionDep
) -> Invoice:
    issuer = await _current_issuer(session, tenant)
    client = await _find_client(payload.client_id, session, tenant)
    repo = InvoiceRepository(session, tenant.id)
    serial, invoice_number = await _resolve_number(payload, session, tenant, repo)

    invoice = Invoice(
        owner=tenant,
        issuer=issuer,
        recipient=await _recipient_from(client, tenant),
        issue_date=payload.issue_date,
        invoice_number=invoice_number,
        serial_id=serial.id if serial else None,
        state=payload.state,
        notes=payload.notes,
        due_date=payload.due_date,
        payment_method=payload.payment_method,
        retention_rate=payload.retention_rate,
    )
    for line in payload.lines:
        invoice.add_line(InvoiceLine(**line.model_dump()))

    await repo.add(invoice)
    await session.commit()
    return await repo.reload(invoice)


@invoice_router.put(
    "/{invoice_id}",
    response_model=InvoiceRead,
    summary="Update a draft invoice",
    description=(
        "Replaces a DRAFT invoice (lines included). With `clientId` the recipient becomes a "
        "fresh copy of that client; without it the current recipient is kept. Sending "
        "`state: ISSUED` issues it, assigning the next number of its serial. Issued invoices "
        "are immutable."
    ),
)
async def update_invoice(
    tenant: CurrentTenant, invoice_id: int, payload: InvoiceUpdate, session: SessionDep
) -> Invoice:
    repo = InvoiceRepository(session, tenant.id)
    invoice = await repo.find(invoice_id)
    if invoice is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
    if invoice.state is InvoiceState.ISSUED:
        raise HTTPException(status.HTTP_409_CONFLICT, "An issued invoice can no longer be modified")

    issuer = await _current_issuer(session, tenant)
    if payload.client_id is not None:
        client = await _find_client(payload.client_id, session, tenant)
        await _refresh_recipient(invoice, client, session, tenant)
    serial, invoice.invoice_number = await _resolve_number(payload, session, tenant, repo)
    invoice.serial_id = serial.id if serial else None
    invoice.issuer = issuer  # drafts follow the current fiscal data until issued
    invoice.issue_date = payload.issue_date
    invoice.state = payload.state
    invoice.notes = payload.notes
    invoice.due_date = payload.due_date
    invoice.payment_method = payload.payment_method
    invoice.retention_rate = payload.retention_rate

    invoice.lines.clear()  # replaced wholesale; orphans are deleted by the cascade
    for line in payload.lines:
        invoice.add_line(InvoiceLine(**line.model_dump()))

    await session.commit()
    return await repo.reload(invoice)
