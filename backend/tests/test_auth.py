"""Authentication: login / logout / session cookie and the account activation flow."""

import re
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.account_status import AccountStatus
from app.accounts.models import User
from app.accounts.security import (
    create_session_token,
    hash_password,
    read_session_token,
    verify_password,
)
from app.core.config import get_settings
from app.core.mail import InMemoryMailer
from app.fixtures import UserFactory
from tests.conftest import PASSWORD, login

COOKIE = get_settings().session_cookie_name
LINK_PATTERN = re.compile(r"http://test/activate/(?P<token>[A-Za-z0-9_-]+)")


def activation_token(mailer: InMemoryMailer, index: int = -1) -> str:
    """The token inside the link of the `index`-th e-mail sent."""
    mail = mailer.outbox[index]
    match = LINK_PATTERN.search(mail.text)
    assert match, mail.text
    assert match.group(0) in (mail.html or ""), "the HTML part must carry the same link"
    return match.group("token")


# -- unit: security primitives ----------------------------------------------------------


def test_password_hashing() -> None:
    hashed = hash_password("s3cret", rounds=4)
    assert hashed != "s3cret" and hashed.startswith("$2b$04$")
    assert verify_password("s3cret", hashed)
    assert not verify_password("S3cret", hashed)
    assert not verify_password("s3cret", None)
    assert not verify_password("s3cret", "not-a-hash")


def test_session_tokens_round_trip_and_expire() -> None:
    settings = get_settings()
    token = create_session_token(42, settings)
    assert read_session_token(token, settings) == 42
    assert read_session_token(token + "x", settings) is None
    assert read_session_token("", settings) is None

    expired = settings.model_copy(update={"session_ttl_hours": -1})
    assert read_session_token(create_session_token(42, expired), settings) is None
    other_key = settings.model_copy(update={"secret_key": "another-secret-key-of-32-bytes!!"})
    assert read_session_token(create_session_token(42, other_key), settings) is None


# -- login / logout ---------------------------------------------------------------------


async def test_health_and_docs_are_public_but_nothing_else(client: AsyncClient) -> None:
    assert (await client.get("/api/health")).status_code == 200
    assert (await client.get("/api/docs")).status_code == 200
    for method, path in (
        ("GET", "/api/auth/me"),
        ("GET", "/api/invoice"),
        ("POST", "/api/subject"),
        ("GET", "/api/admin/user"),
        ("GET", "/api/admin/settings"),
    ):
        response = await client.request(method, path)
        assert response.status_code == 401, (method, path, response.text)
        assert response.json() == {"detail": "Authentication required"}


async def test_login_sets_a_session_cookie(client: AsyncClient, tenant: User) -> None:
    assert (await client.get("/api/auth/me")).status_code == 401

    # The e-mail is case-insensitive and surrounding blanks are ignored
    response = await client.post(
        "/api/auth/login", json={"email": "  Tenant@Example.COM ", "password": PASSWORD}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["email"] == "tenant@example.com"
    assert (body["role"], body["status"]) == ("ADMIN", "ACTIVE")
    assert body["hasPassword"] is True
    assert body["lastLoginAt"] is not None
    assert "passwordHash" not in body and "password_hash" not in body

    cookie = response.cookies.get(COOKIE)
    assert cookie
    set_cookie = response.headers["set-cookie"]
    assert "HttpOnly" in set_cookie and "SameSite=lax" in set_cookie.replace("Lax", "lax")
    assert read_session_token(cookie, get_settings()) == tenant.id

    me = await client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["id"] == tenant.id

    logout = await client.post("/api/auth/logout")
    assert logout.status_code == 204
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_login_rejects_bad_credentials(client: AsyncClient, tenant: User) -> None:
    async def attempt(email: str, password: str) -> int:
        response = await client.post("/api/auth/login", json={"email": email, "password": password})
        if response.status_code == 401:
            assert response.json()["detail"] == "Invalid e-mail or password"
        return response.status_code

    assert await attempt(tenant.email, "wrong-password") == 401
    assert await attempt("nobody@example.com", PASSWORD) == 401  # same answer: no enumeration
    assert await attempt("not-an-email", PASSWORD) == 422
    assert await attempt(tenant.email, "") == 422
    assert COOKIE not in client.cookies


async def test_accounts_without_a_password_cannot_log_in(
    client: AsyncClient, user_factory: type[UserFactory], session: AsyncSession
) -> None:
    pending = user_factory(status=AccountStatus.ACTIVE)  # activated by hand, no password yet
    await session.flush()
    response = await client.post("/api/auth/login", json={"email": pending.email, "password": "x"})
    assert response.status_code == 401


async def test_paused_accounts_cannot_log_in(
    client: AsyncClient, user_factory: type[UserFactory], session: AsyncSession
) -> None:
    paused = user_factory(status=AccountStatus.PAUSED, password_hash=hash_password(PASSWORD, 4))
    await session.flush()

    response = await client.post(
        "/api/auth/login", json={"email": paused.email, "password": PASSWORD}
    )
    assert response.status_code == 403
    assert "paused" in response.json()["detail"]
    assert COOKIE not in client.cookies
    # ... even with a wrong password the answer is still the generic one
    response = await client.post("/api/auth/login", json={"email": paused.email, "password": "no"})
    assert response.status_code == 401


async def test_pausing_an_account_ends_its_sessions(
    tenant_client: AsyncClient, tenant: User, session: AsyncSession
) -> None:
    assert (await tenant_client.get("/api/invoice")).status_code == 200
    tenant.status = AccountStatus.PAUSED
    await session.flush()
    assert (await tenant_client.get("/api/invoice")).status_code == 401


async def test_forged_or_stale_cookies_are_ignored(
    client: AsyncClient, tenant: User, session: AsyncSession
) -> None:
    client.cookies.set(COOKIE, "garbage")
    assert (await client.get("/api/auth/me")).status_code == 401

    client.cookies.set(COOKIE, create_session_token(tenant.id, get_settings()))
    assert (await client.get("/api/auth/me")).status_code == 200
    client.cookies.set(COOKIE, create_session_token(tenant.id + 1000, get_settings()))
    assert (await client.get("/api/auth/me")).status_code == 401  # account gone


# -- account activation -----------------------------------------------------------------


async def test_activation_flow(
    client: AsyncClient, super_admin_client: AsyncClient, mailer: InMemoryMailer
) -> None:
    created = await super_admin_client.post(
        "/api/admin/user", json={"email": "ana@empresa.es", "name": "Ana"}
    )
    assert created.status_code == 201, created.text
    assert (created.json()["status"], created.json()["hasPassword"]) == ("PAUSED", False)
    expires_at = datetime.fromisoformat(created.json()["activationExpiresAt"])
    assert timedelta(hours=23) < expires_at - datetime.now(UTC) <= timedelta(hours=24)

    # One e-mail, to the new user, carrying the link
    assert [mail.to for mail in mailer.outbox] == ["ana@empresa.es"]
    assert mailer.outbox[0].subject == "Activa tu cuenta de Isofactu"
    assert "Hola Ana," in mailer.outbox[0].text
    assert "24 horas" in mailer.outbox[0].text
    token = activation_token(mailer)

    # The page first checks the link and learns who it is for
    info = await client.get(f"/api/auth/activate/{token}")
    assert info.status_code == 200, info.text
    assert info.json()["email"] == "ana@empresa.es"
    assert (await client.get("/api/auth/activate/not-a-token")).status_code == 404

    # Until the password is chosen the account cannot log in
    assert (
        await client.post("/api/auth/login", json={"email": "ana@empresa.es", "password": "x"})
    ).status_code == 401

    # Weak passwords are refused and the link stays usable
    weak = await client.post(f"/api/auth/activate/{token}", json={"password": "short"})
    assert weak.status_code == 422
    assert "at least 8 characters" in weak.json()["detail"][0]["msg"]
    too_long = await client.post(f"/api/auth/activate/{token}", json={"password": "ñ" * 40})
    assert too_long.status_code == 422  # 80 bytes > bcrypt's 72
    assert (await client.get(f"/api/auth/activate/{token}")).status_code == 200

    # Setting the password activates the account and consumes the link
    done = await client.post(f"/api/auth/activate/{token}", json={"password": "ana-pass-123"})
    assert done.status_code == 200, done.text
    body = done.json()
    assert (body["status"], body["hasPassword"], body["activationExpiresAt"]) == (
        "ACTIVE",
        True,
        None,
    )
    assert (await client.get(f"/api/auth/activate/{token}")).status_code == 404
    reused = await client.post(f"/api/auth/activate/{token}", json={"password": "other-pass-1"})
    assert reused.status_code == 404

    # ... and the new credentials work (activation itself does not log the user in)
    assert (await client.get("/api/auth/me")).status_code == 401
    login = await client.post(
        "/api/auth/login", json={"email": "ana@empresa.es", "password": "ana-pass-123"}
    )
    assert login.status_code == 200, login.text
    assert (await client.get("/api/invoice")).json()["total"] == 0


async def test_expired_links_are_refused(
    client: AsyncClient,
    super_admin_client: AsyncClient,
    mailer: InMemoryMailer,
    session: AsyncSession,
) -> None:
    created = await super_admin_client.post("/api/admin/user", json={"email": "ana@empresa.es"})
    token = activation_token(mailer)
    user = await session.get(User, created.json()["id"])
    assert user is not None and user.activation_token is not None
    user.activation_token.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await session.flush()

    assert (await client.get(f"/api/auth/activate/{token}")).status_code == 404
    refused = await client.post(f"/api/auth/activate/{token}", json={"password": "ana-pass-123"})
    assert refused.status_code == 404
    await session.refresh(user)
    assert (user.status, user.has_password) == (AccountStatus.PAUSED, False)

    # The admin panel still shows the (expired) link so that it can be re-sent
    listed = (await super_admin_client.get(f"/api/admin/user/{user.id}")).json()
    assert datetime.fromisoformat(listed["activationExpiresAt"]) < datetime.now(UTC)


async def test_resending_replaces_the_previous_link(
    client: AsyncClient, super_admin_client: AsyncClient, mailer: InMemoryMailer
) -> None:
    created = await super_admin_client.post("/api/admin/user", json={"email": "ana@empresa.es"})
    user_id = created.json()["id"]
    first = activation_token(mailer)

    resent = await super_admin_client.post(f"/api/admin/user/{user_id}/send-activation")
    assert resent.status_code == 200, resent.text
    assert len(mailer.outbox) == 2
    second = activation_token(mailer)
    assert second != first

    assert (await client.get(f"/api/auth/activate/{first}")).status_code == 404
    assert (await client.get(f"/api/auth/activate/{second}")).status_code == 200


async def test_resending_lets_an_active_user_choose_a_new_password(
    client: AsyncClient, super_admin_client: AsyncClient, tenant: User, mailer: InMemoryMailer
) -> None:
    resent = await super_admin_client.post(f"/api/admin/user/{tenant.id}/send-activation")
    assert resent.status_code == 200, resent.text
    token = activation_token(mailer)

    # The old password keeps working until the link is used
    await login(client, tenant)
    await client.post("/api/auth/logout")

    done = await client.post(f"/api/auth/activate/{token}", json={"password": "brand-new-pass"})
    assert done.status_code == 200, done.text
    old = await client.post("/api/auth/login", json={"email": tenant.email, "password": PASSWORD})
    assert old.status_code == 401
    await login(client, tenant, "brand-new-pass")


async def test_pausing_revokes_the_activation_link(
    client: AsyncClient, super_admin_client: AsyncClient, mailer: InMemoryMailer
) -> None:
    created = await super_admin_client.post("/api/admin/user", json={"email": "ana@empresa.es"})
    user_id = created.json()["id"]
    token = activation_token(mailer)

    # Pausing an account that is already paused is harmless, but it drops the link
    paused = await super_admin_client.post(f"/api/admin/user/{user_id}/pause")
    assert paused.status_code == 200, paused.text
    assert paused.json()["activationExpiresAt"] is None
    assert (await client.get(f"/api/auth/activate/{token}")).status_code == 404

    # A manual activation does not hand out a password: the link has to be re-sent
    activated = await super_admin_client.post(f"/api/admin/user/{user_id}/activate")
    assert (activated.json()["status"], activated.json()["hasPassword"]) == ("ACTIVE", False)
    assert (
        await client.post("/api/auth/login", json={"email": "ana@empresa.es", "password": "x"})
    ).status_code == 401


@pytest.mark.parametrize("hours", [1, 72])
async def test_link_lifetime_follows_the_system_setting(
    super_admin_client: AsyncClient, mailer: InMemoryMailer, hours: int
) -> None:
    updated = await super_admin_client.put(
        "/api/admin/settings", json={"activationLinkTtlHours": hours}
    )
    assert updated.status_code == 200, updated.text
    assert updated.json() == {"activationLinkTtlHours": hours}

    created = await super_admin_client.post("/api/admin/user", json={"email": "ana@empresa.es"})
    expires_at = datetime.fromisoformat(created.json()["activationExpiresAt"])
    remaining = expires_at - datetime.now(UTC)
    assert timedelta(hours=hours - 1) < remaining <= timedelta(hours=hours)
    assert f"{hours} horas" in mailer.outbox[-1].text


# -- own password -----------------------------------------------------------------------


async def _change_own_password(logged: AsyncClient, client: AsyncClient) -> None:
    me = (await logged.get("/api/auth/me")).json()

    wrong = await logged.post(
        "/api/auth/password", json={"currentPassword": "nope", "newPassword": "brand-new-pass"}
    )
    assert wrong.status_code == 400, wrong.text
    assert "current password" in wrong.json()["detail"]
    weak = await logged.post(
        "/api/auth/password", json={"currentPassword": PASSWORD, "newPassword": "short"}
    )
    assert weak.status_code == 422
    assert weak.json()["detail"][0]["loc"] == ["body", "newPassword"]

    changed = await logged.post(
        "/api/auth/password", json={"currentPassword": PASSWORD, "newPassword": "brand-new-pass"}
    )
    assert changed.status_code == 204, changed.text
    assert (await logged.get("/api/auth/me")).status_code == 200  # the session survives

    old = await client.post("/api/auth/login", json={"email": me["email"], "password": PASSWORD})
    assert old.status_code == 401
    new = await client.post(
        "/api/auth/login", json={"email": me["email"], "password": "brand-new-pass"}
    )
    assert new.status_code == 200


async def test_tenants_change_their_own_password(
    tenant_client: AsyncClient, client: AsyncClient
) -> None:
    await _change_own_password(tenant_client, client)


async def test_super_admins_change_their_own_password(
    super_admin_client: AsyncClient, client: AsyncClient
) -> None:
    await _change_own_password(super_admin_client, client)


async def test_changing_the_password_requires_a_session(client: AsyncClient) -> None:
    response = await client.post(
        "/api/auth/password", json={"currentPassword": "x", "newPassword": "brand-new-pass"}
    )
    assert response.status_code == 401
