"""Account management by SUPER_ADMIN users (`/api/admin`)."""

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.models import User
from app.clients.models import Client
from app.core.mail import InMemoryMailer, Mail, MailDeliveryError
from app.fixtures import ClientFactory, InvoiceFactory
from app.invoicing.models import Invoice, Subject


async def test_only_super_admins_manage_accounts(
    tenant_client: AsyncClient, tenant: User, other_tenant: User
) -> None:
    forbidden = [
        ("GET", "/api/admin/user"),
        ("POST", "/api/admin/user"),
        ("GET", f"/api/admin/user/{other_tenant.id}"),
        ("PUT", f"/api/admin/user/{other_tenant.id}"),
        ("DELETE", f"/api/admin/user/{other_tenant.id}"),
        ("POST", f"/api/admin/user/{other_tenant.id}/pause"),
        ("POST", f"/api/admin/user/{other_tenant.id}/activate"),
        ("POST", f"/api/admin/user/{other_tenant.id}/send-activation"),
        ("GET", "/api/admin/settings"),
        ("PUT", "/api/admin/settings"),
    ]
    for method, path in forbidden:
        response = await tenant_client.request(method, path, json={})
        assert response.status_code == 403, (method, path, response.text)
        assert response.json() == {"detail": "SUPER_ADMIN role required"}


async def test_list_and_get_accounts(
    super_admin_client: AsyncClient, super_admin: User, tenant: User
) -> None:
    response = await super_admin_client.get("/api/admin/user")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 2
    assert [u["email"] for u in body["items"]] == ["root@example.com", "tenant@example.com"]
    assert set(body["items"][0]) == {
        "id",
        "email",
        "name",
        "role",
        "status",
        "hasPassword",
        "activationExpiresAt",
        "createdAt",
        "lastLoginAt",
    }

    response = await super_admin_client.get("/api/admin/user", params={"limit": 1, "offset": 1})
    page = response.json()
    assert (page["total"], [u["id"] for u in page["items"]]) == (2, [tenant.id])

    one = await super_admin_client.get(f"/api/admin/user/{tenant.id}")
    assert one.status_code == 200
    assert (one.json()["email"], one.json()["role"]) == ("tenant@example.com", "ADMIN")
    assert (await super_admin_client.get("/api/admin/user/999")).status_code == 404


async def test_create_account(super_admin_client: AsyncClient, mailer: InMemoryMailer) -> None:
    response = await super_admin_client.post(
        "/api/admin/user", json={"email": " Ana@Empresa.ES ", "name": "Ana García"}
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["email"] == "ana@empresa.es"  # normalised
    assert (body["name"], body["role"], body["status"]) == ("Ana García", "ADMIN", "PAUSED")
    assert body["hasPassword"] is False
    assert body["activationExpiresAt"] is not None
    assert body["lastLoginAt"] is None
    assert len(mailer.outbox) == 1

    # Another SUPER_ADMIN can be created the same way
    root = await super_admin_client.post(
        "/api/admin/user", json={"email": "root2@example.com", "role": "SUPER_ADMIN"}
    )
    assert root.status_code == 201, root.text
    assert root.json()["role"] == "SUPER_ADMIN"

    duplicate = await super_admin_client.post("/api/admin/user", json={"email": "ANA@empresa.es"})
    assert duplicate.status_code == 409
    assert "already exists" in duplicate.json()["detail"]

    invalid = await super_admin_client.post("/api/admin/user", json={"email": "ana"})
    assert invalid.status_code == 422
    assert invalid.json()["detail"][0]["loc"] == ["body", "email"]
    invalid = await super_admin_client.post(
        "/api/admin/user", json={"email": "x@y.es", "role": "GOD"}
    )
    assert invalid.status_code == 422
    assert len(mailer.outbox) == 2  # nothing sent for the failed attempts


async def test_creation_is_rolled_back_when_the_mail_cannot_be_sent(
    app, super_admin_client: AsyncClient, session: AsyncSession
) -> None:
    class BrokenMailer:
        async def send(self, mail: Mail) -> None:
            raise MailDeliveryError("connection refused")

    from app.core.mail import get_mailer

    app.dependency_overrides[get_mailer] = BrokenMailer
    response = await super_admin_client.post("/api/admin/user", json={"email": "ana@empresa.es"})
    assert response.status_code == 503, response.text
    assert "could not be sent" in response.json()["detail"]
    count = select(func.count()).select_from(User).where(User.email == "ana@empresa.es")
    assert await session.scalar(count) == 0


async def test_update_account(
    super_admin_client: AsyncClient, tenant: User, other_tenant: User
) -> None:
    response = await super_admin_client.put(
        f"/api/admin/user/{tenant.id}",
        json={"email": "New@Example.com", "name": "Renamed", "role": "ADMIN"},
    )
    assert response.status_code == 200, response.text
    assert (response.json()["email"], response.json()["name"]) == ("new@example.com", "Renamed")

    # Keeping the same e-mail is fine; taking someone else's is not
    same = await super_admin_client.put(
        f"/api/admin/user/{tenant.id}", json={"email": "new@example.com", "name": "Renamed"}
    )
    assert same.status_code == 200
    taken = await super_admin_client.put(
        f"/api/admin/user/{tenant.id}", json={"email": other_tenant.email, "name": "Renamed"}
    )
    assert taken.status_code == 409

    # Roles can be changed (e.g. promoting a tenant)
    promoted = await super_admin_client.put(
        f"/api/admin/user/{tenant.id}", json={"email": "new@example.com", "role": "SUPER_ADMIN"}
    )
    assert promoted.json()["role"] == "SUPER_ADMIN"

    assert (
        await super_admin_client.put("/api/admin/user/999", json={"email": "x@example.com"})
    ).status_code == 404


async def test_pause_and_activate(
    super_admin_client: AsyncClient, client: AsyncClient, tenant: User
) -> None:
    paused = await super_admin_client.post(f"/api/admin/user/{tenant.id}/pause")
    assert paused.status_code == 200, paused.text
    assert paused.json()["status"] == "PAUSED"
    from tests.conftest import PASSWORD

    refused = await client.post(
        "/api/auth/login", json={"email": tenant.email, "password": PASSWORD}
    )
    assert refused.status_code == 403

    activated = await super_admin_client.post(f"/api/admin/user/{tenant.id}/activate")
    assert activated.status_code == 200, activated.text
    assert activated.json()["status"] == "ACTIVE"
    allowed = await client.post(
        "/api/auth/login", json={"email": tenant.email, "password": PASSWORD}
    )
    assert allowed.status_code == 200

    assert (await super_admin_client.post("/api/admin/user/999/pause")).status_code == 404
    assert (await super_admin_client.post("/api/admin/user/999/activate")).status_code == 404
    assert (await super_admin_client.post("/api/admin/user/999/send-activation")).status_code == 404


async def test_delete_account_removes_its_data(
    super_admin_client: AsyncClient,
    tenant: User,
    other_tenant: User,
    invoice_factory: type[InvoiceFactory],
    client_factory: type[ClientFactory],
    session: AsyncSession,
) -> None:
    invoice_factory.create_batch(2, owner=tenant, lines=1)
    client_factory(owner=tenant)
    client_factory(owner=other_tenant)
    kept = invoice_factory(owner=other_tenant, lines=1)
    await session.flush()

    response = await super_admin_client.delete(f"/api/admin/user/{tenant.id}")
    assert response.status_code == 204, response.text
    assert (await super_admin_client.get(f"/api/admin/user/{tenant.id}")).status_code == 404
    assert (await super_admin_client.delete(f"/api/admin/user/{tenant.id}")).status_code == 404

    # The database cascades: the tenant's invoices, recipients and clients are gone, the
    # other's stay
    assert await session.scalar(select(func.count()).select_from(Invoice)) == 1
    assert await session.scalar(select(func.count()).select_from(Subject)) == 1
    assert await session.scalar(select(func.count()).select_from(Client)) == 1
    assert (await session.scalar(select(Invoice.id).where(Invoice.id == kept.id))) == kept.id


async def test_super_admins_cannot_lock_themselves_out(
    super_admin_client: AsyncClient, super_admin: User
) -> None:
    me = super_admin.id
    assert (await super_admin_client.post(f"/api/admin/user/{me}/pause")).status_code == 400
    assert (await super_admin_client.delete(f"/api/admin/user/{me}")).status_code == 400
    demoted = await super_admin_client.put(
        f"/api/admin/user/{me}", json={"email": super_admin.email, "role": "ADMIN"}
    )
    assert demoted.status_code == 400
    # Editing one's own name / e-mail is fine, as long as the role stays
    renamed = await super_admin_client.put(
        f"/api/admin/user/{me}",
        json={"email": super_admin.email, "name": "Me", "role": "SUPER_ADMIN"},
    )
    assert renamed.status_code == 200, renamed.text
    assert (await super_admin_client.get("/api/auth/me")).json()["name"] == "Me"


async def test_system_settings(super_admin_client: AsyncClient) -> None:
    assert (await super_admin_client.get("/api/admin/settings")).json() == {
        "activationLinkTtlHours": 24
    }
    updated = await super_admin_client.put(
        "/api/admin/settings", json={"activationLinkTtlHours": 48}
    )
    assert updated.status_code == 200, updated.text
    assert (await super_admin_client.get("/api/admin/settings")).json() == {
        "activationLinkTtlHours": 48
    }
    for invalid in (0, -1, 24 * 31, "soon"):
        response = await super_admin_client.put(
            "/api/admin/settings", json={"activationLinkTtlHours": invalid}
        )
        assert response.status_code == 422, invalid
