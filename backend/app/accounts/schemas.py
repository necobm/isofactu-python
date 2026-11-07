"""Pydantic schemas of the Accounts module (API contract, camelCase JSON)."""

import re
from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, Field

from app.accounts.account_status import AccountStatus
from app.accounts.role import Role
from app.accounts.security import PASSWORD_MAX_BYTES, PASSWORD_MIN_LENGTH
from app.core.schemas import ApiModel

# Deliberately lenient (one "@", something on both sides, a dot in the domain): the
# activation e-mail is the real proof that an address works, and development addresses
# such as `admin@isofactu.local` must be accepted.
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normalise_email(value: str) -> str:
    value = value.strip().lower()
    if not EMAIL_PATTERN.match(value):
        raise ValueError("value is not a valid e-mail address")
    return value


def _check_password(value: str) -> str:
    if len(value) < PASSWORD_MIN_LENGTH:
        raise ValueError(f"the password must have at least {PASSWORD_MIN_LENGTH} characters")
    if len(value.encode()) > PASSWORD_MAX_BYTES:
        raise ValueError(f"the password cannot be longer than {PASSWORD_MAX_BYTES} bytes")
    return value


Email = Annotated[
    str, Field(max_length=255, examples=["ana@empresa.es"]), AfterValidator(_normalise_email)
]
Password = Annotated[str, Field(examples=["s3cret-pass"]), AfterValidator(_check_password)]


# -- users ----------------------------------------------------------------------------


class UserRead(ApiModel):
    id: int
    email: str
    name: str
    role: Role
    status: AccountStatus
    has_password: bool = Field(
        description="False until the user sets a password through the activation link"
    )
    activation_expires_at: datetime | None = Field(
        description="Expiry of the outstanding activation link, `null` when there is none"
    )
    created_at: datetime
    last_login_at: datetime | None


class UserCollection(ApiModel):
    items: list[UserRead]
    total: int
    limit: int
    offset: int


class UserCreate(ApiModel):
    email: Email
    name: str = Field(default="", max_length=255, examples=["Ana García"])
    role: Role = Role.ADMIN


class UserUpdate(ApiModel):
    email: Email
    name: str = Field(default="", max_length=255)
    role: Role = Role.ADMIN


# -- authentication -------------------------------------------------------------------


class LoginRequest(ApiModel):
    email: Email
    password: str = Field(min_length=1, examples=["s3cret-pass"])


class PasswordChange(ApiModel):
    current_password: str = Field(min_length=1)
    new_password: Password


class ActivationInfo(ApiModel):
    """What the activation page shows before the password is chosen."""

    email: str
    name: str
    expires_at: datetime


class ActivationRequest(ApiModel):
    password: Password


# -- system settings ------------------------------------------------------------------


class SystemSettings(ApiModel):
    activation_link_ttl_hours: int = Field(
        ge=1,
        le=24 * 30,
        description="How long activation links stay valid. Applies to links issued from now on.",
        examples=[24],
    )
