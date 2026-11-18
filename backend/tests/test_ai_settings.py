"""Each tenant's AI vendor (`/api/ai-settings`), the encryption of its API key, and the
invoice extractor built from it."""

from datetime import date

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.models import User
from app.ai.models import AiSettings
from app.ai.providers import PROVIDERS, catalog_models
from app.core.config import Settings
from app.core.crypto import (
    SecretBox,
    SecretDecryptionError,
    derived_key,
    generate_key,
    get_secret_box,
    secret_box_for,
)
from app.invoicing.extraction import LiteLLMInvoiceExtractor, get_invoice_extractor

API_KEY = "sk-ant-api03-0123456789abcdef"
OTHER_KEY = "sk-proj-ZYXWVUTSRQPONMLK9876"
AZURE_ENDPOINT = "https://acme-invoices.openai.azure.com"


async def _models(client: AsyncClient, provider: str) -> list[dict]:
    response = await client.get(f"/api/ai-settings/providers/{provider}/models")
    assert response.status_code == 200, response.text
    return response.json()


async def _first_model(client: AsyncClient, provider: str) -> str:
    """A model of the provider that reads PDFs (whatever the installed LiteLLM offers)."""
    models = await _models(client, provider)
    assert models[0]["readsPdf"]
    return models[0]["id"]


async def _stored(session: AsyncSession) -> AiSettings:
    settings = await session.scalar(select(AiSettings))
    assert settings is not None
    await session.refresh(settings)
    return settings


# -- providers and models -------------------------------------------------------------------


async def test_providers(tenant_client: AsyncClient) -> None:
    response = await tenant_client.get("/api/ai-settings/providers")
    assert response.status_code == 200
    assert [(p["id"], p["needsEndpoint"], p["needsRegion"]) for p in response.json()] == [
        ("gemini", False, False),
        ("anthropic", False, False),
        ("openai", False, False),
        ("azure", True, False),
        ("bedrock", False, True),
    ]


@pytest.mark.parametrize("provider", list(PROVIDERS))
async def test_each_provider_offers_its_models(tenant_client: AsyncClient, provider: str) -> None:
    models = await _models(tenant_client, provider)
    assert models, provider
    ids = [m["id"] for m in models]
    assert len(ids) == len(set(ids))
    assert not any("/" in i or i.startswith("ft:") for i in ids)  # no duplicates / templates
    # Those that read PDFs (scans too) come first
    reads_pdf = [m["readsPdf"] for m in models]
    assert reads_pdf == sorted(reads_pdf, reverse=True)


async def test_models_of_an_unknown_provider(tenant_client: AsyncClient) -> None:
    response = await tenant_client.get("/api/ai-settings/providers/ollama/models")
    assert response.status_code == 404


def test_the_catalogue_is_filtered() -> None:
    catalog = {
        "claude-b-1": {"litellm_provider": "anthropic", "mode": "chat"},
        "anthropic/claude-a-2": {
            "litellm_provider": "anthropic",
            "mode": "chat",
            "supports_pdf_input": True,
        },
        "claude-a-10": {
            "litellm_provider": "anthropic",
            "mode": "chat",
            "supports_pdf_input": True,
            "supports_response_schema": True,
        },
        "claude-old": {
            "litellm_provider": "anthropic",
            "mode": "chat",
            "deprecation_date": "2026-01-01",
        },
        "claude-embed": {"litellm_provider": "anthropic", "mode": "embedding"},
        "gpt-4o": {"litellm_provider": "openai", "mode": "chat"},
        "ft:claude-a-2": {"litellm_provider": "anthropic", "mode": "chat"},
        "anthropic/eu/claude-a-2": {"litellm_provider": "anthropic", "mode": "chat"},
        "not-a-dict": "x",
    }
    models = catalog_models(PROVIDERS["anthropic"], catalog, date(2026, 6, 1))  # type: ignore[arg-type]
    assert [(m.id, m.reads_pdf, m.structured_output) for m in models] == [
        ("claude-a-10", True, True),  # PDF readers first, newest-looking first (10 > 2)
        ("claude-a-2", True, False),
        ("claude-b-1", False, False),
    ]


def test_bedrock_merges_both_catalogues() -> None:
    catalog = {
        "eu.anthropic.claude-x-v1:0": {"litellm_provider": "bedrock", "mode": "chat"},
        "bedrock/eu.anthropic.claude-x-v1:0": {
            "litellm_provider": "bedrock_converse",
            "mode": "chat",
            "supports_pdf_input": True,
        },
        "bedrock/us-east-1/meta.llama3-8b-instruct-v1:0": {
            "litellm_provider": "bedrock",
            "mode": "chat",
        },
    }
    models = catalog_models(PROVIDERS["bedrock"], catalog, date(2026, 6, 1))
    assert [(m.id, m.reads_pdf) for m in models] == [("eu.anthropic.claude-x-v1:0", True)]


# -- settings -------------------------------------------------------------------------------


async def test_set_up_the_ai_settings(tenant_client: AsyncClient, session: AsyncSession) -> None:
    assert (await tenant_client.get("/api/ai-settings")).json() is None
    model = await _first_model(tenant_client, "anthropic")

    response = await tenant_client.put(
        "/api/ai-settings",
        json={"provider": "anthropic", "model": model, "apiKey": f"  {API_KEY} "},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert {k: body[k] for k in ("provider", "model", "apiKeyHint", "apiKeyReadable")} == {
        "provider": "anthropic",
        "model": model,
        "apiKeyHint": "…cdef",
        "apiKeyReadable": True,
    }
    assert body["readsPdf"] is True
    assert (body["endpoint"], body["apiVersion"], body["deployment"], body["region"]) == (
        "",
        "",
        "",
        "",
    )
    assert API_KEY not in response.text  # the key never comes back
    assert (await tenant_client.get("/api/ai-settings")).json() == body

    # Stored encrypted, never in clear
    stored = await _stored(session)
    assert API_KEY not in stored.api_key_encrypted
    assert get_secret_box().decrypt(stored.api_key_encrypted) == API_KEY


async def test_the_api_key_is_required_to_start_with(tenant_client: AsyncClient) -> None:
    model = await _first_model(tenant_client, "openai")
    for payload in ({}, {"apiKey": ""}, {"apiKey": "   "}):
        response = await tenant_client.put(
            "/api/ai-settings", json={"provider": "openai", "model": model, **payload}
        )
        assert response.status_code == 422, payload
        assert response.json()["detail"][0]["loc"] == ["body", "apiKey"]
    response = await tenant_client.put(
        "/api/ai-settings", json={"provider": "openai", "model": model, "apiKey": "sk- 12 34"}
    )
    assert response.status_code == 422


async def test_changing_the_model_keeps_the_key(
    tenant_client: AsyncClient, session: AsyncSession
) -> None:
    first, second = [m["id"] for m in (await _models(tenant_client, "anthropic"))[:2]]
    await tenant_client.put(
        "/api/ai-settings", json={"provider": "anthropic", "model": first, "apiKey": API_KEY}
    )

    response = await tenant_client.put(
        "/api/ai-settings", json={"provider": "anthropic", "model": second}
    )

    assert response.status_code == 200, response.text
    assert (response.json()["model"], response.json()["apiKeyHint"]) == (second, "…cdef")
    assert get_secret_box().decrypt((await _stored(session)).api_key_encrypted) == API_KEY


async def test_changing_the_provider_needs_its_key(
    tenant_client: AsyncClient, session: AsyncSession
) -> None:
    await tenant_client.put(
        "/api/ai-settings",
        json={
            "provider": "anthropic",
            "model": await _first_model(tenant_client, "anthropic"),
            "apiKey": API_KEY,
        },
    )
    gpt = await _first_model(tenant_client, "openai")

    response = await tenant_client.put(
        "/api/ai-settings", json={"provider": "openai", "model": gpt}
    )
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "apiKey"]

    response = await tenant_client.put(
        "/api/ai-settings",
        # fields another provider needs are not kept
        json={"provider": "openai", "model": gpt, "apiKey": OTHER_KEY, "region": "eu-west-1"},
    )
    assert response.status_code == 200, response.text
    assert (response.json()["provider"], response.json()["apiKeyHint"]) == ("openai", "…9876")
    assert response.json()["region"] == ""
    assert get_secret_box().decrypt((await _stored(session)).api_key_encrypted) == OTHER_KEY


async def test_provider_and_model_must_be_known(tenant_client: AsyncClient) -> None:
    async def put(**payload) -> AsyncClient:
        return await tenant_client.put("/api/ai-settings", json={"apiKey": API_KEY, **payload})

    response = await put(provider="ollama", model="llama3.1")
    assert response.status_code == 422
    response = await put(provider="anthropic", model="gpt-4o")  # another provider's model
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "model"]
    assert (await tenant_client.get("/api/ai-settings")).json() is None


async def test_azure_needs_its_resource(tenant_client: AsyncClient) -> None:
    model = await _first_model(tenant_client, "azure")

    async def put(**fields) -> dict:
        payload = {"provider": "azure", "model": model, "apiKey": API_KEY, **fields}
        response = await tenant_client.put("/api/ai-settings", json=payload)
        return {"status": response.status_code, "body": response.json()}

    assert (await put())["status"] == 422  # no endpoint
    # Only the https endpoint of an Azure resource: the server calls it with the key
    for endpoint in (
        "http://acme.openai.azure.com",
        "https://acme.openai.azure.com.evil.example",
        "https://evil.example/acme.openai.azure.com",
        "https://acme.openai.azure.com/openai/deployments",
        "https://user:pass@acme.openai.azure.com",
        "https://acme.openai.azure.com:8443",
        "https://169.254.169.254",
        "https://localhost",
    ):
        assert (await put(endpoint=endpoint))["status"] == 422, endpoint
    assert (await put(endpoint=AZURE_ENDPOINT, apiVersion="yesterday"))["status"] == 422
    assert (await put(endpoint=AZURE_ENDPOINT, deployment="my deployment"))["status"] == 422

    saved = await put(
        endpoint="https://ACME-invoices.openai.azure.com/",
        apiVersion="2024-10-21",
        deployment="invoices-prod",
    )
    assert saved["status"] == 200, saved
    assert (
        saved["body"]["endpoint"],
        saved["body"]["apiVersion"],
        saved["body"]["deployment"],
    ) == (
        AZURE_ENDPOINT,  # normalised
        "2024-10-21",
        "invoices-prod",
    )

    # An Azure key belongs to its resource: another endpoint needs its key
    other = "https://other.cognitiveservices.azure.com"
    response = await tenant_client.put(
        "/api/ai-settings", json={"provider": "azure", "model": model, "endpoint": other}
    )
    assert response.status_code == 422
    response = await tenant_client.put(
        "/api/ai-settings", json={"provider": "azure", "model": model, "endpoint": AZURE_ENDPOINT}
    )
    assert response.status_code == 200  # same resource: the key is kept


async def test_bedrock_needs_a_region(tenant_client: AsyncClient) -> None:
    model = await _first_model(tenant_client, "bedrock")
    base = {"provider": "bedrock", "model": model, "apiKey": API_KEY}
    for region in ("", "europe", "eu-west-1; rm -rf"):
        response = await tenant_client.put("/api/ai-settings", json={**base, "region": region})
        assert response.status_code == 422, region
    response = await tenant_client.put(
        "/api/ai-settings", json={**base, "region": "eu-west-1", "endpoint": AZURE_ENDPOINT}
    )
    assert response.status_code == 200, response.text
    assert (response.json()["region"], response.json()["endpoint"]) == ("eu-west-1", "")


async def test_short_keys_are_not_hinted(tenant_client: AsyncClient) -> None:
    model = await _first_model(tenant_client, "gemini")
    response = await tenant_client.put(
        "/api/ai-settings", json={"provider": "gemini", "model": model, "apiKey": "abc12345"}
    )
    assert (response.json()["apiKeyHint"], response.json()["apiKeyReadable"]) == (None, True)


async def test_remove_the_ai_settings(tenant_client: AsyncClient, session: AsyncSession) -> None:
    model = await _first_model(tenant_client, "gemini")
    await tenant_client.put(
        "/api/ai-settings", json={"provider": "gemini", "model": model, "apiKey": API_KEY}
    )

    assert (await tenant_client.delete("/api/ai-settings")).status_code == 204
    assert (await tenant_client.get("/api/ai-settings")).json() is None
    assert await session.scalar(select(AiSettings)) is None
    assert (await tenant_client.delete("/api/ai-settings")).status_code == 204  # idempotent


async def test_settings_are_per_tenant(
    app, tenant_client: AsyncClient, other_tenant: User, session: AsyncSession
) -> None:
    from tests.conftest import _make_client, login

    model = await _first_model(tenant_client, "anthropic")
    await tenant_client.put(
        "/api/ai-settings", json={"provider": "anthropic", "model": model, "apiKey": API_KEY}
    )
    async with _make_client(app) as other:
        await login(other, other_tenant)
        assert (await other.get("/api/ai-settings")).json() is None
        # Its own key is not the first tenant's, and removing its settings touches nothing else
        await other.put(
            "/api/ai-settings", json={"provider": "anthropic", "model": model, "apiKey": OTHER_KEY}
        )
        assert (await other.get("/api/ai-settings")).json()["apiKeyHint"] == "…9876"
        assert (await other.delete("/api/ai-settings")).status_code == 204
    assert (await tenant_client.get("/api/ai-settings")).json()["apiKeyHint"] == "…cdef"


async def test_only_tenants_have_ai_settings(
    client: AsyncClient, super_admin_client: AsyncClient
) -> None:
    for method, path in (
        ("GET", "/api/ai-settings"),
        ("PUT", "/api/ai-settings"),
        ("DELETE", "/api/ai-settings"),
        ("GET", "/api/ai-settings/providers"),
        ("GET", "/api/ai-settings/providers/openai/models"),
    ):
        assert (await client.request(method, path)).status_code == 401, path
        assert (await super_admin_client.request(method, path)).status_code == 403, path


async def test_deleting_the_account_deletes_its_settings(
    tenant_client: AsyncClient,
    super_admin_client: AsyncClient,
    tenant: User,
    session: AsyncSession,
) -> None:
    model = await _first_model(tenant_client, "openai")
    await tenant_client.put(
        "/api/ai-settings", json={"provider": "openai", "model": model, "apiKey": API_KEY}
    )
    assert (await super_admin_client.delete(f"/api/admin/user/{tenant.id}")).status_code == 204
    assert await session.scalar(select(AiSettings)) is None


# -- a key that can no longer be decrypted --------------------------------------------------


async def test_a_key_that_cannot_be_decrypted(
    tenant_client: AsyncClient, session: AsyncSession, tenant: User
) -> None:
    model = await _first_model(tenant_client, "anthropic")
    await tenant_client.put(
        "/api/ai-settings", json={"provider": "anthropic", "model": model, "apiKey": API_KEY}
    )
    # As if the server's encryption keys had changed since it was stored
    stored = await _stored(session)
    stored.api_key_encrypted = SecretBox([generate_key().encode()]).encrypt(API_KEY)
    await session.flush()

    body = (await tenant_client.get("/api/ai-settings")).json()
    assert (body["apiKeyReadable"], body["apiKeyHint"]) == (False, None)
    # It must be entered again: saving without it is refused ...
    response = await tenant_client.put(
        "/api/ai-settings", json={"provider": "anthropic", "model": model}
    )
    assert response.status_code == 422
    # ... and PDF import says so
    with pytest.raises(HTTPException) as error:
        await get_invoice_extractor(tenant, session)
    assert error.value.status_code == 503
    assert "decrypted" in error.value.detail

    response = await tenant_client.put(
        "/api/ai-settings", json={"provider": "anthropic", "model": model, "apiKey": API_KEY}
    )
    assert response.json()["apiKeyReadable"] is True


# -- the extractor follows the tenant's settings --------------------------------------------


async def test_no_settings_no_extractor(tenant: User, session: AsyncSession) -> None:
    assert await get_invoice_extractor(tenant, session) is None


async def test_the_extractor_uses_the_tenants_settings(
    tenant_client: AsyncClient, tenant: User, session: AsyncSession
) -> None:
    model = await _first_model(tenant_client, "anthropic")
    await tenant_client.put(
        "/api/ai-settings", json={"provider": "anthropic", "model": model, "apiKey": API_KEY}
    )

    extractor = await get_invoice_extractor(tenant, session)

    assert isinstance(extractor, LiteLLMInvoiceExtractor)
    assert (extractor.model, extractor.api_key, extractor.api_base, extractor.params) == (
        f"anthropic/{model}",
        API_KEY,
        None,  # the vendor's own endpoint
        {},
    )
    assert extractor.reads_pdf


async def test_the_extractor_on_azure_and_bedrock(
    tenant_client: AsyncClient, tenant: User, session: AsyncSession
) -> None:
    azure_model = await _first_model(tenant_client, "azure")
    await tenant_client.put(
        "/api/ai-settings",
        json={
            "provider": "azure",
            "model": azure_model,
            "apiKey": API_KEY,
            "endpoint": AZURE_ENDPOINT,
            "apiVersion": "2024-10-21",
            "deployment": "invoices-prod",
        },
    )
    extractor = await get_invoice_extractor(tenant, session)
    assert isinstance(extractor, LiteLLMInvoiceExtractor)
    assert (extractor.model, extractor.capabilities_model) == (
        "azure/invoices-prod",
        f"azure/{azure_model}",
    )
    assert (extractor.api_base, extractor.params) == (
        AZURE_ENDPOINT,
        {"api_version": "2024-10-21"},
    )
    assert extractor.reads_pdf  # known from the model the deployment runs

    bedrock_model = await _first_model(tenant_client, "bedrock")
    await tenant_client.put(
        "/api/ai-settings",
        json={
            "provider": "bedrock",
            "model": bedrock_model,
            "apiKey": OTHER_KEY,
            "region": "eu-west-1",
        },
    )
    extractor = await get_invoice_extractor(tenant, session)
    assert isinstance(extractor, LiteLLMInvoiceExtractor)
    assert (extractor.model, extractor.api_key, extractor.params) == (
        f"bedrock/{bedrock_model}",
        OTHER_KEY,
        {"aws_region_name": "eu-west-1"},
    )


async def test_pdf_import_is_unavailable_without_settings(
    tenant_client: AsyncClient, fiscal_data
) -> None:
    files = {"file": ("factura.pdf", b"%PDF-1.7\n%%EOF", "application/pdf")}
    response = await tenant_client.post("/api/received-invoice/extract", files=files)
    assert response.status_code == 503
    assert "AI provider" in response.json()["detail"]


# -- encryption -----------------------------------------------------------------------------


def test_secrets_round_trip_with_a_fresh_iv_each_time() -> None:
    box = SecretBox([generate_key().encode()])
    first, second = box.encrypt(API_KEY), box.encrypt(API_KEY)
    assert first != second
    assert box.decrypt(first) == box.decrypt(second) == API_KEY
    with pytest.raises(SecretDecryptionError):
        box.decrypt(first[:-4] + "AAAA")  # tampered
    with pytest.raises(SecretDecryptionError):
        SecretBox([generate_key().encode()]).decrypt(first)  # another key


def test_keys_can_be_rotated() -> None:
    secret = "s" * 40
    old, new = generate_key(), generate_key()
    # Stored before ENCRYPTION_KEYS was configured: with the key derived from SECRET_KEY
    before = secret_box_for(Settings(secret_key=secret, encryption_keys="")).encrypt(API_KEY)
    stored_with_old = secret_box_for(Settings(secret_key=secret, encryption_keys=old)).encrypt(
        API_KEY
    )

    # New key first, old one kept: everything still reads (the derived key is always last)
    box = secret_box_for(Settings(secret_key=secret, encryption_keys=f"{new}, {old}"))
    assert box.decrypt(before) == box.decrypt(stored_with_old) == API_KEY

    # After rotating, the new key alone is enough
    rotated = box.rotate(stored_with_old)
    assert SecretBox([new.encode()]).decrypt(rotated) == API_KEY
    with pytest.raises(SecretDecryptionError):
        SecretBox([old.encode(), derived_key(secret)]).decrypt(rotated)


def test_encryption_keys_are_validated() -> None:
    with pytest.raises(ValueError, match="Fernet"):
        Settings(encryption_keys="not-a-key")
    assert Settings(encryption_keys=f" {generate_key()} ,").encryption_key_list
