"""Data access for the Clients module, bound to a tenant."""

from collections.abc import Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.models import Client

LIKE_ESCAPE = "\\"


def _contains(term: str) -> str:
    """`LIKE` pattern matching `term` anywhere, with LIKE metacharacters escaped."""
    for char in (LIKE_ESCAPE, "%", "_"):
        term = term.replace(char, LIKE_ESCAPE + char)
    return f"%{term}%"


class ClientRepository:
    def __init__(self, session: AsyncSession, owner_id: int) -> None:
        self.session = session
        self.owner_id = owner_id

    def _query(self, search: str | None):
        stmt = select(Client).where(Client.owner_id == self.owner_id)
        if search and (term := search.strip()):
            pattern = _contains(term)
            columns = Client.__table__.c
            stmt = stmt.where(
                or_(
                    Client.full_name.ilike(pattern, escape=LIKE_ESCAPE),
                    columns.document_number.ilike(pattern, escape=LIKE_ESCAPE),
                )
            )
        return stmt

    async def find_all(
        self, *, search: str | None = None, limit: int = 50, offset: int = 0
    ) -> Sequence[Client]:
        """Clients ordered by name; `search` matches the name or the document number."""
        stmt = self._query(search).order_by(Client.full_name, Client.id).limit(limit).offset(offset)
        return (await self.session.scalars(stmt)).all()

    async def count(self, *, search: str | None = None) -> int:
        stmt = select(func.count()).select_from(self._query(search).subquery())
        return await self.session.scalar(stmt) or 0

    async def find(self, client_id: int) -> Client | None:
        stmt = select(Client).where(Client.id == client_id, Client.owner_id == self.owner_id)
        return await self.session.scalar(stmt)

    async def add(self, client: Client) -> Client:
        self.session.add(client)
        await self.session.flush()
        return client

    async def delete(self, client: Client) -> None:
        await self.session.delete(client)
        await self.session.flush()
