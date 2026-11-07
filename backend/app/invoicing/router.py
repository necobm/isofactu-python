"""HTTP endpoints of the Invoicing module.

Every endpoint requires a logged-in ADMIN (the tenant) and only touches that tenant's
data: the repositories are bound to the current user.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.deps import CurrentTenant
from app.accounts.models import User
from app.clients.models import Client
from app.clients.repository import ClientRepository
from app.core.config import get_settings
from app.core.database import get_session
from app.invoicing.extraction import (
    ExtractionError,
    InvoiceExtractor,
    UnreadablePdf,
    draft_from,
    get_invoice_extractor,
)
from app.invoicing.invoice_kind import InvoiceKind
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
    InvoiceCollectionStatus,
    InvoiceContent,
    InvoiceCreate,
    InvoiceRead,
    InvoiceUpdate,
    InvoiceWrite,
    ReceivedInvoiceCreate,
    ReceivedInvoiceDraft,
    ReceivedInvoiceUpdate,
    ReceivedInvoiceWrite,
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
invoice_router = APIRouter(prefix="/invoice", tags=["Issued invoices"])
received_invoice_router = APIRouter(prefix="/received-invoice", tags=["Received invoices"])


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


# -- invoices: shared helpers ----------------------------------------------------------


async def _current_fiscal_data(session: AsyncSession, tenant: User) -> FiscalData:
    """The account's fiscal data -- the issuer of its issued invoices and the recipient of
    its received ones -- or a 409 until it is set up."""
    data = await FiscalDataRepository(session, tenant.id).get()
    if data is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Set up the fiscal data of the account before creating invoices",
        )
    return data


def _validation_error(field: str, message: str, type_: str = "value_error") -> HTTPException:
    return HTTPException(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        [{"loc": ["body", field], "msg": message, "type": type_}],
    )


def _copy_into(
    subject: Subject, full_name: str, document: IdentificationDocument, address: Address
) -> Subject:
    subject.full_name = full_name
    subject.document = document
    subject.address = address
    return subject


async def _refresh_recipient(
    invoice: Invoice,
    full_name: str,
    document: IdentificationDocument,
    address: Address,
    session: AsyncSession,
    tenant: User,
) -> None:
    """Make a draft's recipient a copy of the given party. The existing copy is reused when
    this is the only invoice holding it; a copy shared with other invoices (legacy data) is
    left alone and a fresh one is made."""
    repo = SubjectRepository(session, tenant.id)
    if await repo.reference_count(invoice.recipient) == 1:
        _copy_into(invoice.recipient, full_name, document, address)
    else:
        invoice.recipient = _copy_into(Subject(owner=tenant), full_name, document, address)


def _replace_content(invoice: Invoice, payload: InvoiceContent) -> None:
    """Copy what every invoice has (dates, payment, notes, retention, lines) from the
    payload; lines are replaced wholesale and orphans deleted by the cascade."""
    invoice.issue_date = payload.issue_date
    invoice.notes = payload.notes
    invoice.due_date = payload.due_date
    invoice.payment_method = payload.payment_method
    invoice.retention_rate = payload.retention_rate
    invoice.lines.clear()
    for line in payload.lines:
        invoice.add_line(InvoiceLine(**line.model_dump()))


async def _list(
    repo: InvoiceRepository, state: InvoiceState | None, limit: int, offset: int
) -> InvoiceCollection:
    items = await repo.find_all(state=state, limit=limit, offset=offset)
    return InvoiceCollection(
        items=[InvoiceRead.model_validate(i) for i in items],
        total=await repo.count(state=state),
        limit=limit,
        offset=offset,
    )


async def _find_invoice(repo: InvoiceRepository, invoice_id: int) -> Invoice:
    invoice = await repo.find(invoice_id)
    if invoice is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
    return invoice


async def _find_draft(repo: InvoiceRepository, invoice_id: int) -> Invoice:
    invoice = await _find_invoice(repo, invoice_id)
    if invoice.state is InvoiceState.ISSUED:
        raise HTTPException(status.HTTP_409_CONFLICT, "An issued invoice can no longer be modified")
    return invoice


# -- issued invoices (income) ---------------------------------------------------------


@invoice_router.get(
    "",
    response_model=InvoiceCollection,
    summary="List issued invoices",
    description=(
        "Returns the collection of invoices issued by the account, newest first. "
        "Optionally restricted to a single state with `?state=`. Received invoices are "
        "listed under `/api/received-invoice`."
    ),
)
async def list_invoices(
    tenant: CurrentTenant,
    session: SessionDep,
    state: StateParam = None,
    limit: LimitParam = 50,
    offset: OffsetParam = 0,
) -> InvoiceCollection:
    return await _list(InvoiceRepository(session, tenant.id), state, limit, offset)


@invoice_router.get("/{invoice_id}", response_model=InvoiceRead, summary="Get an issued invoice")
async def get_invoice(tenant: CurrentTenant, invoice_id: int, session: SessionDep) -> Invoice:
    return await _find_invoice(InvoiceRepository(session, tenant.id), invoice_id)


async def _find_client(client_id: int, session: AsyncSession, tenant: User) -> Client:
    """The client referenced by the payload, or a 422. Clients of other tenants count as
    missing."""
    client = await ClientRepository(session, tenant.id).find(client_id)
    if client is None:
        raise _validation_error("clientId", "Client not found")
    return client


def _recipient_from(client: Client, tenant: User) -> Subject:
    """The invoice's own copy of the client: no reference is kept to the client, so editing
    or deleting it later never changes the invoice."""
    return _copy_into(Subject(owner=tenant), client.full_name, client.document, client.address)


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
    summary="Create an issued invoice",
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
    issuer = (await _current_fiscal_data(session, tenant)).as_issuer()
    client = await _find_client(payload.client_id, session, tenant)
    repo = InvoiceRepository(session, tenant.id)
    serial, invoice_number = await _resolve_number(payload, session, tenant, repo)

    invoice = Invoice(
        owner=tenant,
        kind=InvoiceKind.ISSUED,
        issuer=issuer,
        recipient=_recipient_from(client, tenant),
        invoice_number=invoice_number,
        serial_id=serial.id if serial else None,
        state=payload.state,
    )
    _replace_content(invoice, payload)

    await repo.add(invoice)
    await session.commit()
    return await repo.reload(invoice)


@invoice_router.put(
    "/{invoice_id}",
    response_model=InvoiceRead,
    summary="Update a draft issued invoice",
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
    invoice = await _find_draft(repo, invoice_id)

    issuer = (await _current_fiscal_data(session, tenant)).as_issuer()
    if payload.client_id is not None:
        client = await _find_client(payload.client_id, session, tenant)
        await _refresh_recipient(
            invoice, client.full_name, client.document, client.address, session, tenant
        )
    serial, invoice.invoice_number = await _resolve_number(payload, session, tenant, repo)
    invoice.serial_id = serial.id if serial else None
    invoice.issuer = issuer  # drafts follow the current fiscal data until issued
    invoice.state = payload.state
    _replace_content(invoice, payload)

    await session.commit()
    return await repo.reload(invoice)


@invoice_router.put(
    "/{invoice_id}/collection",
    response_model=InvoiceRead,
    summary="Record whether an issued invoice was collected",
    description=(
        "Sets the day the client paid an ISSUED invoice (`collectedOn`), or `null` to mark it "
        "as pending collection again. This is not part of the invoice content, so it can be "
        "changed after issuing. `409` for drafts; `422` for a date before the issue date or "
        "in the future."
    ),
)
async def set_invoice_collection(
    tenant: CurrentTenant, invoice_id: int, payload: InvoiceCollectionStatus, session: SessionDep
) -> Invoice:
    repo = InvoiceRepository(session, tenant.id)
    invoice = await _find_invoice(repo, invoice_id)
    if invoice.state is not InvoiceState.ISSUED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only issued invoices can be collected")
    if payload.collected_on is not None and payload.collected_on < invoice.issue_date:
        raise _validation_error("collectedOn", "collectedOn cannot be earlier than the issue date")
    invoice.collected_on = payload.collected_on
    await session.commit()
    return await repo.reload(invoice)


# -- received invoices (expenses) -----------------------------------------------------
# A received invoice has no lifecycle: it was issued by the supplier before the tenant
# records it, so it is stored as ISSUED right away and can be corrected at any time.


def _received_repo(session: AsyncSession, tenant: User) -> InvoiceRepository:
    return InvoiceRepository(session, tenant.id, InvoiceKind.RECEIVED)


def _supplier(payload: ReceivedInvoiceWrite) -> Issuer:
    return Issuer.of(
        payload.issuer.full_name,
        IdentificationDocument(**payload.issuer.document.model_dump()),
        Address(**payload.issuer.address.model_dump()),
    )


@received_invoice_router.get(
    "",
    response_model=InvoiceCollection,
    summary="List received invoices",
    description="The invoices received from suppliers (expenses), newest first.",
)
async def list_received_invoices(
    tenant: CurrentTenant,
    session: SessionDep,
    limit: LimitParam = 50,
    offset: OffsetParam = 0,
) -> InvoiceCollection:
    return await _list(_received_repo(session, tenant), None, limit, offset)


@received_invoice_router.get(
    "/{invoice_id}", response_model=InvoiceRead, summary="Get a received invoice"
)
async def get_received_invoice(
    tenant: CurrentTenant, invoice_id: int, session: SessionDep
) -> Invoice:
    return await _find_invoice(_received_repo(session, tenant), invoice_id)


@received_invoice_router.post(
    "",
    response_model=InvoiceRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a received invoice",
    description=(
        "Records a supplier's invoice. The supplier (`issuer`) and its number (required) are "
        "stored as entered; the recipient is a copy of the account's fiscal data (`409` until "
        "it is set up)."
    ),
)
async def create_received_invoice(
    tenant: CurrentTenant, payload: ReceivedInvoiceCreate, session: SessionDep
) -> Invoice:
    account = await _current_fiscal_data(session, tenant)
    repo = _received_repo(session, tenant)
    invoice = Invoice(
        owner=tenant,
        kind=InvoiceKind.RECEIVED,
        state=InvoiceState.ISSUED,
        issuer=_supplier(payload),
        recipient=_copy_into(
            Subject(owner=tenant), account.company_name, account.document, account.address
        ),
        invoice_number=InvoiceNumber(**payload.invoice_number.model_dump()),
    )
    _replace_content(invoice, payload)

    await repo.add(invoice)
    await session.commit()
    return await repo.reload(invoice)


@received_invoice_router.put(
    "/{invoice_id}",
    response_model=InvoiceRead,
    summary="Update a received invoice",
    description=(
        "Replaces a received invoice (supplier, number and lines included). Received "
        "invoices can always be edited. The recipient stays the copy of the fiscal data "
        "taken when the invoice was recorded."
    ),
)
async def update_received_invoice(
    tenant: CurrentTenant, invoice_id: int, payload: ReceivedInvoiceUpdate, session: SessionDep
) -> Invoice:
    repo = _received_repo(session, tenant)
    invoice = await _find_invoice(repo, invoice_id)
    invoice.issuer = _supplier(payload)
    invoice.invoice_number = InvoiceNumber(**payload.invoice_number.model_dump())
    _replace_content(invoice, payload)

    await session.commit()
    return await repo.reload(invoice)


ExtractorDep = Annotated[InvoiceExtractor | None, Depends(get_invoice_extractor)]
PDF_MAGIC = b"%PDF-"


@received_invoice_router.post(
    "/extract",
    response_model=ReceivedInvoiceDraft,
    summary="Read a received invoice from a PDF",
    description=(
        "Reads the supplier, number, dates, lines, VAT and IRPF of the uploaded invoice (any "
        "layout) with the configured LLM, so that the form can be pre-filled. **Nothing is "
        "stored**: review the draft and save it with `POST /api/received-invoice`. The PDF is "
        "sent to the LLM vendor. `503` when PDF import is not configured, `413` when the file "
        "is too large, `422` when it cannot be used (`type`: `not_pdf`, `no_text` -- a scan "
        "and a model that cannot read PDF files --, or `not_invoice`), `502` when the LLM "
        "could not read it."
    ),
)
async def extract_received_invoice(
    tenant: CurrentTenant,
    session: SessionDep,
    extractor: ExtractorDep,
    file: Annotated[UploadFile, File(description="The supplier's invoice, as a PDF")],
) -> ReceivedInvoiceDraft:
    if extractor is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "PDF import is not configured on this server (LLM_PROVIDER / LLM_MODEL)",
        )
    limit = get_settings().invoice_pdf_max_bytes
    pdf = await file.read(limit + 1)
    if len(pdf) > limit:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE, f"The PDF cannot be larger than {limit} bytes"
        )
    if not pdf.startswith(PDF_MAGIC):
        raise _validation_error("file", "The file is not a PDF", "not_pdf")

    account = await FiscalDataRepository(session, tenant.id).get()
    try:
        raw = await extractor.extract(pdf, customer=account.as_issuer() if account else None)
    except UnreadablePdf as exc:
        raise _validation_error("file", str(exc), exc.reason) from exc
    except ExtractionError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "The invoice could not be read from the PDF"
        ) from exc
    if raw.get("is_invoice") is False:
        raise _validation_error("file", "The PDF does not look like an invoice", "not_invoice")
    return draft_from(raw, account)
