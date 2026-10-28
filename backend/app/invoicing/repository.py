"""Data access for the Invoicing module (port of the Doctrine repositories)."""

from collections.abc import Sequence

from sqlalchemy import BigInteger, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.invoicing.invoice_state import InvoiceState
from app.invoicing.models import Invoice, Subject

LIKE_ESCAPE = "\\"


def _contains(term: str) -> str:
    """`LIKE` pattern matching `term` anywhere, with LIKE metacharacters escaped."""
    for char in (LIKE_ESCAPE, "%", "_"):
        term = term.replace(char, LIKE_ESCAPE + char)
    return f"%{term}%"


class SubjectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_all(
        self, *, search: str | None = None, limit: int = 50, offset: int = 0
    ) -> Sequence[Subject]:
        """Subjects ordered by name; `search` matches the name or the document number."""
        stmt = select(Subject).order_by(Subject.full_name, Subject.id).limit(limit).offset(offset)
        if search and (term := search.strip()):
            pattern = _contains(term)
            columns = Subject.__table__.c
            stmt = stmt.where(
                or_(
                    Subject.full_name.ilike(pattern, escape=LIKE_ESCAPE),
                    columns.document_number.ilike(pattern, escape=LIKE_ESCAPE),
                )
            )
        return (await self.session.scalars(stmt)).all()

    async def count(self) -> int:
        return await self.session.scalar(select(func.count()).select_from(Subject)) or 0

    async def find(self, subject_id: int) -> Subject | None:
        return await self.session.get(Subject, subject_id)

    async def add(self, subject: Subject) -> Subject:
        self.session.add(subject)
        await self.session.flush()
        return subject


class InvoiceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_all(
        self, *, state: InvoiceState | None = None, limit: int = 50, offset: int = 0
    ) -> Sequence[Invoice]:
        stmt = (
            select(Invoice)
            .order_by(Invoice.issue_date.desc(), Invoice.id.desc())
            .limit(limit)
            .offset(offset)
        )
        if state is not None:
            stmt = stmt.where(Invoice.state == state)
        return (await self.session.scalars(stmt)).unique().all()

    async def count(self, *, state: InvoiceState | None = None) -> int:
        stmt = select(func.count()).select_from(Invoice)
        if state is not None:
            stmt = stmt.where(Invoice.state == state)
        return await self.session.scalar(stmt) or 0

    async def find(self, invoice_id: int) -> Invoice | None:
        return await self.session.get(Invoice, invoice_id)

    async def next_number(self, serial: str | None) -> str:
        """Next sequential number within `serial` ("1" for an empty serial).

        Numbers are plain integers rendered as strings; non-numeric numbers stored through
        the API are ignored. A transaction-scoped advisory lock serialises concurrent
        callers on the same serial, so two invoices cannot be issued with the same number.
        """
        lock_key = func.hashtext(f"invoice_number:{serial or ''}")
        await self.session.execute(select(func.pg_advisory_xact_lock(lock_key)))

        columns = Invoice.__table__.c
        stmt = select(func.max(cast(columns.number, BigInteger))).where(
            columns.serial == serial if serial else columns.serial.is_(None),
            columns.number.op("~")(r"^\d+$"),
        )
        highest = await self.session.scalar(stmt) or 0
        return str(highest + 1)

    async def add(self, invoice: Invoice) -> Invoice:
        self.session.add(invoice)
        await self.session.flush()
        return invoice

    async def reload(self, invoice: Invoice) -> Invoice:
        """Reload every attribute (relationships included) so the entity can be serialised
        without triggering lazy loads, e.g. right after a commit."""
        await self.session.refresh(invoice)
        return invoice
