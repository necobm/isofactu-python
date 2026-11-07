"""ORM entities of the Accounts module."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.accounts.account_status import AccountStatus
from app.accounts.role import Role
from app.core.database import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class User(Base):
    """A person who can log in. ADMIN users are tenants: every subject and invoice
    belongs to exactly one of them."""

    __tablename__ = "user_account"

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    # Stored lower-cased so that uniqueness is case-insensitive.
    email: Mapped[str] = mapped_column(String(255), unique=True)
    role: Mapped[Role] = mapped_column(
        Enum(Role, name="user_role", native_enum=False, length=20), default=Role.ADMIN
    )
    status: Mapped[AccountStatus] = mapped_column(
        Enum(AccountStatus, name="account_status", native_enum=False, length=10),
        default=AccountStatus.PAUSED,
    )
    name: Mapped[str] = mapped_column(String(255), default="")
    # NULL until the user sets a password (through the activation link).
    password_hash: Mapped[str | None] = mapped_column(Text, default=None, repr=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default_factory=utcnow, repr=False
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None, repr=False
    )
    # The outstanding activation link, if any (at most one per user).
    activation_token: Mapped[ActivationToken | None] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="joined",
        default=None,
        repr=False,
    )

    @property
    def has_password(self) -> bool:
        return self.password_hash is not None

    @property
    def is_active(self) -> bool:
        return self.status is AccountStatus.ACTIVE

    @property
    def is_super_admin(self) -> bool:
        return self.role is Role.SUPER_ADMIN

    @property
    def activation_expires_at(self) -> datetime | None:
        """When the outstanding activation link stops working (`None` if there is none)."""
        return self.activation_token.expires_at if self.activation_token else None

    def __str__(self) -> str:
        return self.email


class ActivationToken(Base):
    """Single-use link letting a user set a password and activate the account.

    Only a SHA-256 hash of the secret is stored: a leaked database does not expose
    working links. Issuing a new token replaces the previous one; consuming it, pausing
    the account or issuing a new one deletes it.
    """

    __tablename__ = "activation_token"

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"), init=False, unique=True
    )
    # Attached from the parent side (`user.activation_token = token`) so that the token
    # cascades into the session together with the user.
    user: Mapped[User] = relationship(back_populates="activation_token", init=False, repr=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, repr=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default_factory=utcnow, repr=False
    )

    def is_expired(self, now: datetime | None = None) -> bool:
        return (now or utcnow()) >= self.expires_at


class AppSetting(Base):
    """System-wide settings editable by a SUPER_ADMIN, stored as key / value."""

    __tablename__ = "app_setting"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
