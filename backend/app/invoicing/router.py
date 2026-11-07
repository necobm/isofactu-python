"""HTTP endpoints of the Invoicing module.

Every endpoint requires a logged-in ADMIN (the tenant) and only touches that tenant's
data: the repositories are bound to the current user.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.deps import CurrentTenant
from app.accounts.models import User
from app.core.database import get_session
from app.invoicing.invoice_state import InvoiceState
from app.invoicing.models import FiscalData, Invoice, InvoiceLine, Subject
from app.invoicing.repository import FiscalDataRepository, InvoiceRepository, SubjectRepository
from app.invoicing.schemas import (
    FiscalDataRead,
    FiscalDataWrite,
    InvoiceCollection,
    InvoiceCreate,
    InvoiceNumberInput,
    InvoiceRead,
    InvoiceUpdate,
    InvoiceWrite,
    SubjectCreate,
    SubjectRead,
)
from app.invoicing.value_objects import Address, IdentificationDocument, InvoiceNumber, Issuer

SessionDep = Annotated[AsyncSession, Depends(get_session)]
LimitParam = Annotated[int, Query(ge=1, le=200, description="Page size")]
OffsetParam = Annotated[int, Query(ge=0, description="Number of items to skip")]
StateParam = Annotated[
    InvoiceState | None, Query(description="Only invoices in this state (DRAFT | ISSUED)")
]
SearchParam = Annotated[
    str | None, Query(max_length=100, description="Match on the name or the document number")
]

fiscal_data_router = APIRouter(prefix="/fiscal-data", tags=["Fiscal data"])
invoice_router = APIRouter(prefix="/invoice", tags=["Invoices"])
subject_router = APIRouter(prefix="/subject", tags=["Subjects"])


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


async def _find_recipient(payload: InvoiceWrite, session: AsyncSession, tenant: User) -> Subject:
    """The recipient referenced by the payload, or a 422. Subjects of other tenants count as
    missing."""
    recipient = await SubjectRepository(session, tenant.id).find(payload.recipient_id)
    if recipient is None:
        raise _validation_error("recipientId", "Subject not found")
    return recipient


async def _resolve_number(payload: InvoiceWrite, repo: InvoiceRepository) -> InvoiceNumber:
    """Drafts stay numberless; issued invoices get the requested number, or the next of
    the serial when none is given."""
    if payload.state is InvoiceState.DRAFT:
        if payload.invoice_number is not None:
            raise _validation_error("invoiceNumber", "Draft invoices cannot have an invoice number")
        return InvoiceNumber()
    requested = payload.invoice_number or InvoiceNumberInput()
    number = requested.number or await repo.next_number(requested.serial)
    return InvoiceNumber(requested.serial, number)


@invoice_router.post(
    "",
    response_model=InvoiceRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an invoice",
    description=(
        "Creates a DRAFT (numberless) or an ISSUED invoice. When issuing, the invoice number "
        "is taken from `invoiceNumber`; if its `number` is omitted, the next sequential number "
        "of the given serial is assigned. The issuer is the fiscal data of the account "
        "(`409` until it is set up)."
    ),
)
async def create_invoice(
    tenant: CurrentTenant, payload: InvoiceCreate, session: SessionDep
) -> Invoice:
    issuer = await _current_issuer(session, tenant)
    recipient = await _find_recipient(payload, session, tenant)
    repo = InvoiceRepository(session, tenant.id)
    invoice_number = await _resolve_number(payload, repo)

    invoice = Invoice(
        owner=tenant,
        issuer=issuer,
        recipient=recipient,
        issue_date=payload.issue_date,
        invoice_number=invoice_number,
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
        "Replaces a DRAFT invoice (lines included). Sending `state: ISSUED` issues it, "
        "assigning the next number of the serial. Issued invoices are immutable."
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
    recipient = await _find_recipient(payload, session, tenant)
    invoice.invoice_number = await _resolve_number(payload, repo)
    invoice.issuer = issuer  # drafts follow the current fiscal data until issued
    invoice.recipient = recipient
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


# -- subjects -------------------------------------------------------------------------


@subject_router.get(
    "",
    response_model=list[SubjectRead],
    summary="List subjects",
    description="Subjects ordered by name, optionally filtered with `?q=` (name or document).",
)
async def list_subjects(
    tenant: CurrentTenant,
    session: SessionDep,
    q: SearchParam = None,
    limit: LimitParam = 50,
    offset: OffsetParam = 0,
) -> list[Subject]:
    repo = SubjectRepository(session, tenant.id)
    return list(await repo.find_all(search=q, limit=limit, offset=offset))


@subject_router.get("/{subject_id}", response_model=SubjectRead, summary="Get a subject")
async def get_subject(tenant: CurrentTenant, subject_id: int, session: SessionDep) -> Subject:
    subject = await SubjectRepository(session, tenant.id).find(subject_id)
    if subject is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Subject not found")
    return subject


@subject_router.post(
    "",
    response_model=SubjectRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a subject",
)
async def create_subject(
    tenant: CurrentTenant, payload: SubjectCreate, session: SessionDep
) -> Subject:
    subject = Subject(
        owner=tenant,
        full_name=payload.full_name,
        document=IdentificationDocument(**payload.document.model_dump()),
        address=Address(**payload.address.model_dump()),
    )
    await SubjectRepository(session, tenant.id).add(subject)
    await session.commit()
    return subject
