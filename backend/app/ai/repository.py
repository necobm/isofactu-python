"""Data access of the AI module, scoped to one tenant."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.models import AiSettings


class AiSettingsRepository:
    def __init__(self, session: AsyncSession, owner_id: int) -> None:
        self.session = session
        self.owner_id = owner_id

    async def get(self) -> AiSettings | None:
        stmt = select(AiSettings).where(AiSettings.owner_id == self.owner_id)
        return await self.session.scalar(stmt)

    async def add(self, settings: AiSettings) -> AiSettings:
        self.session.add(settings)
        await self.session.flush()
        return settings

    async def delete(self, settings: AiSettings) -> None:
        await self.session.delete(settings)
        await self.session.flush()


async def all_ai_settings(session: AsyncSession) -> Sequence[AiSettings]:
    """Every tenant's settings: for maintenance only (re-encrypting the API keys)."""
    return (await session.scalars(select(AiSettings).order_by(AiSettings.id))).all()
