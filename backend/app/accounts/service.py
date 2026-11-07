"""Account operations shared by the HTTP API, the CLI and the fixtures.

Everything runs inside the caller's session / transaction: nothing is committed here.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.account_status import AccountStatus
from app.accounts.emails import activation_mail
from app.accounts.models import ActivationToken, User, utcnow
from app.accounts.repository import SystemSettingsRepository, UserRepository
from app.accounts.role import Role
from app.accounts.security import (
    dummy_password_hash,
    generate_activation_token,
    hash_activation_token,
    hash_password_async,
    verify_password_async,
)
from app.core.config import Settings
from app.core.mail import Mailer


class AccountError(Exception):
    """Base class of the domain errors raised by the service."""


class EmailAlreadyTaken(AccountError):
    def __init__(self, email: str) -> None:
        super().__init__(f"An account with the e-mail {email} already exists")
        self.email = email


class InvalidCredentials(AccountError):
    pass


class AccountPaused(AccountError):
    pass


class InvalidActivationToken(AccountError):
    """Unknown, already used or expired activation link."""


def normalise_email(email: str) -> str:
    return email.strip().lower()


class AccountService:
    def __init__(self, session: AsyncSession, settings: Settings, mailer: Mailer) -> None:
        self.session = session
        self.settings = settings
        self.mailer = mailer
        self.users = UserRepository(session)
        self.system_settings = SystemSettingsRepository(session)

    # -- account management (SUPER_ADMIN) ------------------------------------------------

    async def create_account(self, *, email: str, name: str = "", role: Role = Role.ADMIN) -> User:
        """A new, paused account without a password. The activation e-mail is sent right
        away; the caller commits once it has gone out."""
        user = User(email=await self._free_email(email), name=name, role=role)
        await self.users.add(user)
        await self.send_activation_link(user)
        return user

    async def create_super_admin(self, *, email: str, password: str, name: str = "") -> User:
        """Bootstrap: an active SUPER_ADMIN with credentials (no e-mail involved)."""
        user = User(
            email=await self._free_email(email),
            name=name,
            role=Role.SUPER_ADMIN,
            status=AccountStatus.ACTIVE,
            password_hash=await self._hash(password),
        )
        return await self.users.add(user)

    async def update_account(self, user: User, *, email: str, name: str, role: Role) -> User:
        email = normalise_email(email)
        if email != user.email:
            user.email = await self._free_email(email)
        user.name = name
        user.role = role
        await self.session.flush()
        return user

    async def delete_account(self, user: User) -> None:
        """Removes the account together with everything it owns (subjects, invoices)."""
        await self.users.delete(user)

    async def pause(self, user: User) -> User:
        """Paused accounts cannot log in; any outstanding activation link is revoked."""
        user.status = AccountStatus.PAUSED
        user.activation_token = None
        await self.session.flush()
        return user

    async def activate(self, user: User) -> User:
        user.status = AccountStatus.ACTIVE
        await self.session.flush()
        return user

    async def send_activation_link(self, user: User) -> ActivationToken:
        """Issues a fresh activation link (replacing any previous one) and e-mails it."""
        ttl_hours = await self.system_settings.activation_link_ttl_hours()
        if user.activation_token is not None:
            # Drop the previous link first: the unit of work would otherwise INSERT the new
            # row before DELETEing the old one and trip over the one-token-per-user rule.
            user.activation_token = None
            await self.session.flush()
        secret = generate_activation_token()
        token = ActivationToken(
            token_hash=hash_activation_token(secret),
            expires_at=utcnow() + timedelta(hours=ttl_hours),
        )
        user.activation_token = token
        await self.session.flush()
        await self.mailer.send(
            activation_mail(
                to=user.email,
                name=user.name,
                link=self.activation_link(secret),
                expires_at=token.expires_at,
                ttl_hours=ttl_hours,
            )
        )
        return token

    def activation_link(self, secret: str) -> str:
        return f"{self.settings.app_public_url}/activate/{secret}"

    # -- activation (public) -------------------------------------------------------------

    async def find_by_activation_token(self, secret: str) -> User:
        """The user owning a live activation link, or `InvalidActivationToken`."""
        user = await self.users.find_by_activation_token_hash(hash_activation_token(secret))
        if user is None or user.activation_token is None or user.activation_token.is_expired():
            raise InvalidActivationToken()
        return user

    async def activate_with_token(self, secret: str, password: str) -> User:
        """Sets the password, activates the account and consumes the link."""
        user = await self.find_by_activation_token(secret)
        user.password_hash = await self._hash(password)
        user.status = AccountStatus.ACTIVE
        user.activation_token = None
        await self.session.flush()
        return user

    # -- authentication ------------------------------------------------------------------

    async def authenticate(self, email: str, password: str) -> User:
        """The user matching the credentials; `InvalidCredentials` or `AccountPaused`
        otherwise. Unknown e-mails still cost a hash verification (timing)."""
        user = await self.users.find_by_email(email)
        password_hash = (
            user.password_hash
            if user is not None and user.password_hash
            else dummy_password_hash(self.settings.password_hash_rounds)
        )
        valid = await verify_password_async(password, password_hash)
        if user is None or not user.has_password or not valid:
            raise InvalidCredentials()
        if not user.is_active:
            raise AccountPaused()
        user.last_login_at = utcnow()
        await self.session.flush()
        return user

    async def change_password(self, user: User, *, current: str, new: str) -> User:
        """Replaces the password of a logged-in user; `InvalidCredentials` if `current`
        does not match."""
        if not await verify_password_async(current, user.password_hash):
            raise InvalidCredentials()
        user.password_hash = await self._hash(new)
        await self.session.flush()
        return user

    # -- helpers -------------------------------------------------------------------------

    async def _free_email(self, email: str) -> str:
        email = normalise_email(email)
        if await self.users.find_by_email(email) is not None:
            raise EmailAlreadyTaken(email)
        return email

    async def _hash(self, password: str) -> str:
        return await hash_password_async(password, self.settings.password_hash_rounds)
