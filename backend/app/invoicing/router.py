"""HTTP endpoints of the Invoicing module."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.invoicing.invoice_state import InvoiceState
from app.invoicing.models import Invoice, InvoiceLine, Subject
from app.invoicing.repository import InvoiceRepository, SubjectRepository
from app.invoicing.schemas import (
    InvoiceCollection,
    InvoiceCreate,
    InvoiceNumberInput,
    InvoiceRead,
    InvoiceUpdate,
    InvoiceWrite,
    SubjectCreate,
    SubjectRead,
)
from app.invoicing.value_objects import Address, IdentificationDocument, InvoiceNumber

SessionDep = Annotated[AsyncSession, Depends(get_session)]
LimitParam = Annotated[int, Query(ge=1, le=200, description="Page size")]
OffsetParam = Annotated[int, Query(ge=0, description="Number of items to skip")]
StateParam = Annotated[
    InvoiceState | None, Query(description="Only invoices in this state (DRAFT | ISSUED)")
]
SearchParam = Annotated[
    str | None, Query(max_length=100, description="Match on the name or the document number")
]

invoice_router = APIRouter(prefix="/invoice", tags=["Invoices"])
subject_router = APIRouter(prefix="/subject", tags=["Subjects"])


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
    session: SessionDep,
    state: StateParam = None,
    limit: LimitParam = 50,
    offset: OffsetParam = 0,
) -> InvoiceCollection:
    repo = InvoiceRepository(session)
    items = await repo.find_all(state=state, limit=limit, offset=offset)
    total = await repo.count(state=state)
    return InvoiceCollection(
        items=[InvoiceRead.model_validate(i) for i in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@invoice_router.get("/{invoice_id}", response_model=InvoiceRead, summary="Get an invoice")
async def get_invoice(invoice_id: int, session: SessionDep) -> Invoice:
    invoice = await InvoiceRepository(session).find(invoice_id)
    if invoice is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
    return invoice


def _validation_error(field: str, message: str) -> HTTPException:
    return HTTPException(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        [{"loc": ["body", field], "msg": message, "type": "value_error"}],
    )


async def _find_parties(payload: InvoiceWrite, session: AsyncSession) -> tuple[Subject, Subject]:
    """The issuer and recipient referenced by the payload, or a 422 naming the missing one."""
    subjects = SubjectRepository(session)
    issuer = await subjects.find(payload.issuer_id)
    recipient = await subjects.find(payload.recipient_id)
    for field, subject in (("issuerId", issuer), ("recipientId", recipient)):
        if subject is None:
            raise _validation_error(field, "Subject not found")
    return issuer, recipient  # type: ignore[return-value]


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
        "of the given serial is assigned."
    ),
)
async def create_invoice(payload: InvoiceCreate, session: SessionDep) -> Invoice:
    subjects = SubjectRepository(session)
    issuer = await subjects.find(payload.issuer_id)
    recipient = await subjects.find(payload.recipient_id)
    for field, subject in (("issuerId", issuer), ("recipientId", recipient)):
        if subject is None:
            raise _validation_error(field, "Subject not found")

    repo = InvoiceRepository(session)
    if payload.state is InvoiceState.DRAFT:
        if payload.invoice_number is not None:
            raise _validation_error("invoiceNumber", "Draft invoices cannot have an invoice number")
        invoice_number = InvoiceNumber()
    else:
        requested = payload.invoice_number or InvoiceNumberInput()
        number = requested.number or await repo.next_number(requested.serial)
        invoice_number = InvoiceNumber(requested.serial, number)

    invoice = Invoice(
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
async def update_invoice(invoice_id: int, payload: InvoiceUpdate, session: SessionDep) -> Invoice:
    repo = InvoiceRepository(session)
    invoice = await repo.find(invoice_id)
    if invoice is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
    if invoice.state is InvoiceState.ISSUED:
        raise HTTPException(status.HTTP_409_CONFLICT, "An issued invoice can no longer be modified")

    issuer, recipient = await _find_parties(payload, session)
    invoice.invoice_number = await _resolve_number(payload, repo)
    invoice.issuer = issuer
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
    session: SessionDep, q: SearchParam = None, limit: LimitParam = 50, offset: OffsetParam = 0
) -> list[Subject]:
    repo = SubjectRepository(session)
    return list(await repo.find_all(search=q, limit=limit, offset=offset))


@subject_router.get("/{subject_id}", response_model=SubjectRead, summary="Get a subject")
async def get_subject(subject_id: int, session: SessionDep) -> Subject:
    subject = await SubjectRepository(session).find(subject_id)
    if subject is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Subject not found")
    return subject


@subject_router.post(
    "",
    response_model=SubjectRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a subject",
)
async def create_subject(payload: SubjectCreate, session: SessionDep) -> Subject:
    subject = Subject(
        full_name=payload.full_name,
        document=IdentificationDocument(**payload.document.model_dump()),
        address=Address(**payload.address.model_dump()),
    )
    await SubjectRepository(session).add(subject)
    await session.commit()
    return subject
