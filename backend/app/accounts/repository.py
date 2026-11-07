"""Data access for the Accounts module."""

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.models import ActivationToken, AppSetting, User
from app.accounts.role import Role


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_all(self, *, limit: int = 50, offset: int = 0) -> Sequence[User]:
        stmt = select(User).order_by(User.email, User.id).limit(limit).offset(offset)
        return (await self.session.scalars(stmt)).unique().all()

    async def count(self) -> int:
        return await self.session.scalar(select(func.count()).select_from(User)) or 0

    async def find(self, user_id: int) -> User | None:
        # A SELECT rather than `session.get()`: the latter returns an identity-map hit as is,
        # which may lack the eager-loaded activation token (e.g. an object created in this
        # same session); the query populates whatever is still unloaded.
        stmt = select(User).where(User.id == user_id)
        return (await self.session.scalars(stmt)).unique().one_or_none()

    async def find_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email.strip().lower())
        return (await self.session.scalars(stmt)).unique().one_or_none()

    async def find_by_activation_token_hash(self, token_hash: str) -> User | None:
        stmt = (
            select(User).join(User.activation_token).where(ActivationToken.token_hash == token_hash)
        )
        return (await self.session.scalars(stmt)).unique().one_or_none()

    async def exists_with_role(self, role: Role) -> bool:
        stmt = select(func.count()).select_from(User).where(User.role == role)
        return (await self.session.scalar(stmt) or 0) > 0

    async def add(self, user: User) -> User:
        self.session.add(user)
        await self.session.flush()
        # Attributes left at their `None` default (password_hash, activation_token...) are
        # not populated by the dataclass constructor and would lazy-load on first access,
        # which the async session forbids. A refresh loads them all at once.
        await self.session.refresh(user)
        return user

    async def delete(self, user: User) -> None:
        await self.session.delete(user)
        await self.session.flush()

    async def reload(self, user: User) -> User:
        """Reload every attribute (relationships included), e.g. right after a commit."""
        await self.session.refresh(user)
        return user


ACTIVATION_LINK_TTL_HOURS = "activation_link_ttl_hours"
DEFAULT_ACTIVATION_LINK_TTL_HOURS = 24


class SystemSettingsRepository:
    """Typed access to the key / value `app_setting` table."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _get(self, key: str) -> str | None:
        setting = await self.session.get(AppSetting, key)
        return setting.value if setting else None

    async def _set(self, key: str, value: str) -> None:
        setting = await self.session.get(AppSetting, key)
        if setting is None:
            self.session.add(AppSetting(key=key, value=value))
        else:
            setting.value = value
        await self.session.flush()

    async def activation_link_ttl_hours(self) -> int:
        value = await self._get(ACTIVATION_LINK_TTL_HOURS)
        return int(value) if value else DEFAULT_ACTIVATION_LINK_TTL_HOURS

    async def set_activation_link_ttl_hours(self, hours: int) -> None:
        await self._set(ACTIVATION_LINK_TTL_HOURS, str(hours))
