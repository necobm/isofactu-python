"""Data access for the Invoicing module (port of the Doctrine repositories).

Both repositories are bound to a tenant (`owner_id`): every query is restricted to that
tenant's rows, so an invoice or subject of another account is simply "not found".
"""

from collections.abc import Sequence

from sqlalchemy import BigInteger, cast, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.invoicing.invoice_state import InvoiceState
from app.invoicing.models import FiscalData, Invoice, Serial, Subject

LIKE_ESCAPE = "\\"


def _contains(term: str) -> str:
    """`LIKE` pattern matching `term` anywhere, with LIKE metacharacters escaped."""
    for char in (LIKE_ESCAPE, "%", "_"):
        term = term.replace(char, LIKE_ESCAPE + char)
    return f"%{term}%"


class SubjectRepository:
    def __init__(self, session: AsyncSession, owner_id: int) -> None:
        self.session = session
        self.owner_id = owner_id

    async def find_all(
        self, *, search: str | None = None, limit: int = 50, offset: int = 0
    ) -> Sequence[Subject]:
        """Subjects ordered by name; `search` matches the name or the document number."""
        stmt = (
            select(Subject)
            .where(Subject.owner_id == self.owner_id)
            .order_by(Subject.full_name, Subject.id)
            .limit(limit)
            .offset(offset)
        )
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
        stmt = select(func.count()).select_from(Subject).where(Subject.owner_id == self.owner_id)
        return await self.session.scalar(stmt) or 0

    async def find(self, subject_id: int) -> Subject | None:
        stmt = select(Subject).where(Subject.id == subject_id, Subject.owner_id == self.owner_id)
        return await self.session.scalar(stmt)

    async def add(self, subject: Subject) -> Subject:
        self.session.add(subject)
        await self.session.flush()
        return subject


class FiscalDataRepository:
    def __init__(self, session: AsyncSession, owner_id: int) -> None:
        self.session = session
        self.owner_id = owner_id

    async def get(self) -> FiscalData | None:
        stmt = select(FiscalData).where(FiscalData.owner_id == self.owner_id)
        return await self.session.scalar(stmt)

    async def add(self, data: FiscalData) -> FiscalData:
        self.session.add(data)
        await self.session.flush()
        return data


class SerialRepository:
    def __init__(self, session: AsyncSession, owner_id: int) -> None:
        self.session = session
        self.owner_id = owner_id

    async def find_all(self) -> Sequence[Serial]:
        stmt = (
            select(Serial)
            .where(Serial.owner_id == self.owner_id)
            .order_by(Serial.prefix, Serial.suffix, Serial.id)
        )
        return (await self.session.scalars(stmt)).all()

    async def find(self, serial_id: int) -> Serial | None:
        stmt = select(Serial).where(Serial.id == serial_id, Serial.owner_id == self.owner_id)
        return await self.session.scalar(stmt)

    async def find_by_parts(self, prefix: str, suffix: str) -> Serial | None:
        stmt = select(Serial).where(
            Serial.owner_id == self.owner_id, Serial.prefix == prefix, Serial.suffix == suffix
        )
        return await self.session.scalar(stmt)

    async def add(self, serial: Serial) -> Serial:
        self.session.add(serial)
        await self.session.flush()
        return serial

    async def delete(self, serial: Serial) -> None:
        """Drafts that remembered the serial forget it; issued invoices must not exist
        (see `issued_count`)."""
        await self.session.execute(
            update(Invoice).where(Invoice.serial_id == serial.id).values(serial_id=None)
        )
        await self.session.delete(serial)
        await self.session.flush()

    async def usage(self) -> dict[int, tuple[int, int]]:
        """Per serial id: (issued invoices, highest number taken), for those with any."""
        columns = Invoice.__table__.c
        stmt = (
            select(
                columns.serial_id,
                func.count(),
                func.max(cast(columns.number, BigInteger)),
            )
            .where(
                columns.owner_id == self.owner_id,
                columns.serial_id.is_not(None),
                columns.number.op("~")(r"^\d+$"),
            )
            .group_by(columns.serial_id)
        )
        rows = (await self.session.execute(stmt)).all()
        return {serial_id: (count, highest or 0) for serial_id, count, highest in rows}

    async def issued_count(self, serial: Serial) -> int:
        stmt = (
            select(func.count())
            .select_from(Invoice)
            .where(Invoice.serial_id == serial.id, Invoice.__table__.c.number.is_not(None))
        )
        return await self.session.scalar(stmt) or 0


class InvoiceRepository:
    def __init__(self, session: AsyncSession, owner_id: int) -> None:
        self.session = session
        self.owner_id = owner_id

    async def find_all(
        self, *, state: InvoiceState | None = None, limit: int = 50, offset: int = 0
    ) -> Sequence[Invoice]:
        stmt = (
            select(Invoice)
            .where(Invoice.owner_id == self.owner_id)
            .order_by(Invoice.issue_date.desc(), Invoice.id.desc())
            .limit(limit)
            .offset(offset)
        )
        if state is not None:
            stmt = stmt.where(Invoice.state == state)
        return (await self.session.scalars(stmt)).unique().all()

    async def count(self, *, state: InvoiceState | None = None) -> int:
        stmt = select(func.count()).select_from(Invoice).where(Invoice.owner_id == self.owner_id)
        if state is not None:
            stmt = stmt.where(Invoice.state == state)
        return await self.session.scalar(stmt) or 0

    async def find(self, invoice_id: int) -> Invoice | None:
        stmt = select(Invoice).where(Invoice.id == invoice_id, Invoice.owner_id == self.owner_id)
        return (await self.session.scalars(stmt)).unique().one_or_none()

    async def next_number(self, serial: Serial) -> int:
        """Next sequential number of `serial`: its initial number, or one more than the
        highest already taken.

        Numbers are plain integers rendered as strings; non-numeric legacy numbers are
        ignored. A transaction-scoped advisory lock serialises concurrent callers on the
        same serial, so two invoices cannot be issued with the same number.
        """
        lock_key = func.hashtext(f"invoice_number:{serial.id}")
        await self.session.execute(select(func.pg_advisory_xact_lock(lock_key)))

        columns = Invoice.__table__.c
        stmt = select(func.max(cast(columns.number, BigInteger))).where(
            columns.serial_id == serial.id, columns.number.op("~")(r"^\d+$")
        )
        highest = await self.session.scalar(stmt)
        return serial.initial_number if highest is None else max(highest + 1, serial.initial_number)

    async def add(self, invoice: Invoice) -> Invoice:
        self.session.add(invoice)
        await self.session.flush()
        return invoice

    async def reload(self, invoice: Invoice) -> Invoice:
        """Reload every attribute (relationships included) so the entity can be serialised
        without triggering lazy loads, e.g. right after a commit."""
        await self.session.refresh(invoice)
        return invoice
