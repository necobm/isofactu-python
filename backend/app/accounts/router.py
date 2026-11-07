"""HTTP endpoints of the Accounts module.

* `/api/auth/*`  -- login / logout / current user and the public activation flow.
* `/api/admin/*` -- account management and system settings (SUPER_ADMIN only).
"""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.accounts.deps import (
    AccountServiceDep,
    CurrentSuperAdmin,
    CurrentUser,
    SessionDep,
    SettingsDep,
    end_session,
    start_session,
)
from app.accounts.models import User
from app.accounts.repository import SystemSettingsRepository, UserRepository
from app.accounts.schemas import (
    ActivationInfo,
    ActivationRequest,
    LoginRequest,
    PasswordChange,
    SystemSettings,
    UserCollection,
    UserCreate,
    UserRead,
    UserUpdate,
)
from app.accounts.service import (
    AccountPaused,
    EmailAlreadyTaken,
    InvalidActivationToken,
    InvalidCredentials,
)
from app.core.mail import MailDeliveryError

LimitParam = Annotated[int, Query(ge=1, le=200, description="Page size")]
OffsetParam = Annotated[int, Query(ge=0, description="Number of items to skip")]

auth_router = APIRouter(prefix="/auth", tags=["Authentication"])
admin_router = APIRouter(prefix="/admin", tags=["Administration"])


# -- authentication -------------------------------------------------------------------


@auth_router.post(
    "/login",
    response_model=UserRead,
    summary="Log in",
    description=(
        "Checks the credentials and starts a session (HttpOnly cookie). `401` when they do "
        "not match, `403` when they do but the account is paused."
    ),
)
async def login(
    payload: LoginRequest, response: Response, service: AccountServiceDep, settings: SettingsDep
) -> User:
    try:
        user = await service.authenticate(payload.email, payload.password)
    except InvalidCredentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid e-mail or password") from None
    except AccountPaused:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "This account is paused. Contact your administrator."
        ) from None
    await service.session.commit()
    start_session(response, user, settings)
    return user


@auth_router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Log out")
async def logout(response: Response, settings: SettingsDep) -> None:
    end_session(response, settings)


@auth_router.get("/me", response_model=UserRead, summary="Current user")
async def me(user: CurrentUser) -> User:
    return user


@auth_router.post(
    "/password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Change own password",
    description=(
        "Replaces the password of the logged-in user. `400` when `currentPassword` does "
        "not match. Existing sessions stay valid."
    ),
)
async def change_password(
    user: CurrentUser, payload: PasswordChange, service: AccountServiceDep
) -> None:
    try:
        await service.change_password(
            user, current=payload.current_password, new=payload.new_password
        )
    except InvalidCredentials:
        # Deliberately not a 401: that would end the session in the frontend.
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "The current password is incorrect"
        ) from None
    await service.session.commit()


@auth_router.get(
    "/activate/{token}",
    response_model=ActivationInfo,
    summary="Check an activation link",
    description="Who the link is for, or `404` when it is unknown, already used or expired.",
)
async def activation_info(token: str, service: AccountServiceDep) -> ActivationInfo:
    try:
        user = await service.find_by_activation_token(token)
    except InvalidActivationToken:
        raise _invalid_link() from None
    return ActivationInfo(
        email=user.email, name=user.name, expires_at=user.activation_token.expires_at
    )


@auth_router.post(
    "/activate/{token}",
    response_model=UserRead,
    summary="Activate an account",
    description=(
        "Sets the password of the account the link belongs to, activates it and "
        "invalidates the link."
    ),
)
async def activate_account(
    token: str, payload: ActivationRequest, service: AccountServiceDep
) -> User:
    try:
        user = await service.activate_with_token(token, payload.password)
    except InvalidActivationToken:
        raise _invalid_link() from None
    await service.session.commit()
    return await service.users.reload(user)


def _invalid_link() -> HTTPException:
    return HTTPException(
        status.HTTP_404_NOT_FOUND, "This activation link is not valid or has expired"
    )


# -- account management (SUPER_ADMIN) --------------------------------------------------


@admin_router.get("/user", response_model=UserCollection, summary="List accounts")
async def list_users(
    _: CurrentSuperAdmin, session: SessionDep, limit: LimitParam = 50, offset: OffsetParam = 0
) -> UserCollection:
    repo = UserRepository(session)
    items = await repo.find_all(limit=limit, offset=offset)
    return UserCollection(
        items=[UserRead.model_validate(u) for u in items],
        total=await repo.count(),
        limit=limit,
        offset=offset,
    )


@admin_router.post(
    "/user",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account",
    description=(
        "Creates a paused account without a password and e-mails an activation link to it. "
        "`409` when the e-mail is taken, `503` when the e-mail could not be sent (nothing "
        "is created in that case)."
    ),
)
async def create_user(
    _: CurrentSuperAdmin, payload: UserCreate, service: AccountServiceDep
) -> User:
    try:
        user = await service.create_account(
            email=payload.email, name=payload.name, role=payload.role
        )
    except EmailAlreadyTaken as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    except MailDeliveryError:
        await service.session.rollback()
        raise _mail_unavailable() from None
    await service.session.commit()
    return await service.users.reload(user)


@admin_router.get("/user/{user_id}", response_model=UserRead, summary="Get an account")
async def get_user(_: CurrentSuperAdmin, user_id: int, session: SessionDep) -> User:
    return await _find_user(user_id, session)


@admin_router.put("/user/{user_id}", response_model=UserRead, summary="Update an account")
async def update_user(
    current: CurrentSuperAdmin, user_id: int, payload: UserUpdate, service: AccountServiceDep
) -> User:
    user = await _find_user(user_id, service.session)
    if user.id == current.id and payload.role is not current.role:
        raise _self_protection("You cannot change your own role")
    try:
        await service.update_account(
            user, email=payload.email, name=payload.name, role=payload.role
        )
    except EmailAlreadyTaken as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    await service.session.commit()
    return await service.users.reload(user)


@admin_router.delete(
    "/user/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an account",
    description="Removes the account and everything it owns (subjects, invoices).",
)
async def delete_user(current: CurrentSuperAdmin, user_id: int, service: AccountServiceDep) -> None:
    user = await _find_user(user_id, service.session)
    if user.id == current.id:
        raise _self_protection("You cannot delete your own account")
    await service.delete_account(user)
    await service.session.commit()


@admin_router.post(
    "/user/{user_id}/pause",
    response_model=UserRead,
    summary="Pause an account",
    description="The user can no longer log in. Any outstanding activation link is revoked.",
)
async def pause_user(current: CurrentSuperAdmin, user_id: int, service: AccountServiceDep) -> User:
    user = await _find_user(user_id, service.session)
    if user.id == current.id:
        raise _self_protection("You cannot pause your own account")
    await service.pause(user)
    await service.session.commit()
    return await service.users.reload(user)


@admin_router.post(
    "/user/{user_id}/activate", response_model=UserRead, summary="Activate an account"
)
async def activate_user(_: CurrentSuperAdmin, user_id: int, service: AccountServiceDep) -> User:
    user = await _find_user(user_id, service.session)
    await service.activate(user)
    await service.session.commit()
    return await service.users.reload(user)


@admin_router.post(
    "/user/{user_id}/send-activation",
    response_model=UserRead,
    summary="(Re)send the activation link",
    description=(
        "Issues a fresh activation link (the previous one stops working) and e-mails it. "
        "Also the way to let a user choose a new password."
    ),
)
async def send_activation(_: CurrentSuperAdmin, user_id: int, service: AccountServiceDep) -> User:
    user = await _find_user(user_id, service.session)
    try:
        await service.send_activation_link(user)
    except MailDeliveryError:
        await service.session.rollback()
        raise _mail_unavailable() from None
    await service.session.commit()
    return await service.users.reload(user)


# -- system settings ------------------------------------------------------------------


@admin_router.get("/settings", response_model=SystemSettings, summary="System settings")
async def get_settings_(_: CurrentSuperAdmin, session: SessionDep) -> SystemSettings:
    repo = SystemSettingsRepository(session)
    return SystemSettings(activation_link_ttl_hours=await repo.activation_link_ttl_hours())


@admin_router.put("/settings", response_model=SystemSettings, summary="Update system settings")
async def update_settings(
    _: CurrentSuperAdmin, payload: SystemSettings, session: SessionDep
) -> SystemSettings:
    repo = SystemSettingsRepository(session)
    await repo.set_activation_link_ttl_hours(payload.activation_link_ttl_hours)
    await session.commit()
    return SystemSettings(activation_link_ttl_hours=await repo.activation_link_ttl_hours())


# -- helpers --------------------------------------------------------------------------


async def _find_user(user_id: int, session) -> User:
    user = await UserRepository(session).find(user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return user


def _self_protection(message: str) -> HTTPException:
    return HTTPException(status.HTTP_400_BAD_REQUEST, message)


def _mail_unavailable() -> HTTPException:
    return HTTPException(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "The activation e-mail could not be sent. Check the mail server and try again.",
    )
