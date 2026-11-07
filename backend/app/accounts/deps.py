"""FastAPI dependencies: who is calling, and what they are allowed to do.

The session travels in an HttpOnly cookie holding a signed token (see `security.py`).
The user is loaded from the database on every request, so pausing or deleting an account
takes effect immediately.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, Response, status
from fastapi.security import APIKeyCookie
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.models import User
from app.accounts.repository import UserRepository
from app.accounts.role import Role
from app.accounts.security import create_session_token, read_session_token
from app.accounts.service import AccountService
from app.core.config import Settings, get_settings
from app.core.database import get_session
from app.core.mail import Mailer, get_mailer

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
MailerDep = Annotated[Mailer, Depends(get_mailer)]

# Declared as a security scheme so that the OpenAPI docs show which endpoints need a
# session (and "Try it out" works once logged in, the browser sends the cookie itself).
session_cookie = APIKeyCookie(name=get_settings().session_cookie_name, auto_error=False)


def get_account_service(session: SessionDep, settings: SettingsDep, mailer: MailerDep):
    return AccountService(session, settings, mailer)


AccountServiceDep = Annotated[AccountService, Depends(get_account_service)]


async def get_optional_user(
    session: SessionDep,
    settings: SettingsDep,
    token: Annotated[str | None, Depends(session_cookie)],
) -> User | None:
    """The logged-in user, or `None` (no cookie, invalid / expired token, account gone)."""
    if not token:
        return None
    user_id = read_session_token(token, settings)
    if user_id is None:
        return None
    return await UserRepository(session).find(user_id)


async def get_current_user(user: Annotated[User | None, Depends(get_optional_user)]) -> User:
    """An authenticated, active user -- or 401."""
    if user is None or not user.is_active:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Authentication required",
            headers={"WWW-Authenticate": "Cookie"},
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(role: Role):
    async def dependency(user: CurrentUser) -> User:
        if user.role is not role:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"{role.value} role required")
        return user

    return dependency


# The owner of the data being managed (invoices, subjects...).
CurrentTenant = Annotated[User, Depends(require_role(Role.ADMIN))]
# The administrator of the system (accounts, settings).
CurrentSuperAdmin = Annotated[User, Depends(require_role(Role.SUPER_ADMIN))]


# -- session cookie helpers -------------------------------------------------------------


def start_session(response: Response, user: User, settings: Settings) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=create_session_token(user.id, settings),
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def end_session(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.session_cookie_name,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
