"""Testing AI settings before relying on them ("Probar conexión"): `POST /api/ai-settings/test`.

The check is run for real through LiteLLM against a local server posing as each vendor (see
`tests/fake_vendor.py`): no vendor is contacted.
"""

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import router as ai_router_module
from app.ai.models import AiSettings
from app.ai.service import CheckOutcome, ConnectionCheck, LlmConnection, check_connection
from app.core.crypto import get_secret_box
from tests.fake_vendor import FakeVendor, anthropic_reply, openai_reply, vendor_error

KEY = "sk-test-0123456789abcdef"
ANTHROPIC = "anthropic/claude-sonnet-4-5"
OPENAI = "openai/gpt-4o"
AZURE = "azure/invoices-prod"
BEDROCK = "bedrock/eu.anthropic.claude-sonnet-4-5-20250929-v1:0"


def _connection(model: str, vendor: FakeVendor, key: str = KEY) -> LlmConnection:
    params: dict[str, Any] = {}
    if model.startswith("azure/"):
        params = {"api_version": "2024-10-21"}
    elif model.startswith("bedrock/"):
        params = {"aws_region_name": "eu-west-1"}
    return LlmConnection(model, model, key, api_base=vendor.url, params=params)


# -- the check, against fake vendors ----------------------------------------------------------


async def test_a_working_connection(vendor: FakeVendor) -> None:
    vendor.reply(anthropic_reply("OK"))

    result = await check_connection(_connection(ANTHROPIC, vendor), timeout=5)

    assert (result.ok, result.outcome, result.detail) == (True, CheckOutcome.OK, None)
    assert result.latency_ms >= 0
    # A single, minimal request with the tenant's key
    [(path, headers, body)] = vendor.requests
    assert (path, headers["x-api-key"]) == ("/v1/messages", KEY)
    assert body["max_tokens"] == 16
    [message] = body["messages"]
    assert message["content"][0]["text"] == "Reply with the single word OK."


@pytest.mark.parametrize(
    ("model", "status", "body", "outcome"),
    [
        (OPENAI, 200, openai_reply("OK"), CheckOutcome.OK),
        (ANTHROPIC, 401, vendor_error("invalid x-api-key", "authentication_error"), "auth"),
        (
            OPENAI,
            401,
            {
                "error": {
                    "message": "Incorrect API key provided: sk-***1234.",
                    "code": "invalid_api_key",
                }
            },
            "auth",
        ),
        (
            AZURE,
            401,
            {"error": {"code": "401", "message": "Access denied due to invalid subscription key."}},
            "auth",
        ),
        (
            BEDROCK,
            403,
            {"message": "The security token included in the request is invalid."},
            "auth",
        ),
        (
            ANTHROPIC,
            403,
            vendor_error(
                "Your API key does not have permission to use the specified resource.",
                "permission_error",
            ),
            "permission",
        ),
        (
            BEDROCK,
            403,
            {"message": "You don't have access to the model with the specified model ID."},
            "permission",
        ),
        (ANTHROPIC, 404, vendor_error("model: claude-nope", "not_found_error"), "model"),
        (
            OPENAI,
            404,
            {
                "error": {
                    "message": "The model `gpt-nope` does not exist.",
                    "code": "model_not_found",
                }
            },
            "model",
        ),
        (
            AZURE,
            404,
            {
                "error": {
                    "code": "DeploymentNotFound",
                    "message": "The API deployment does not exist.",
                }
            },
            "model",
        ),
        (BEDROCK, 400, {"message": "The provided model identifier is invalid."}, "model"),
        (ANTHROPIC, 429, vendor_error("rate limit exceeded", "rate_limit_error"), "quota"),
        (
            OPENAI,
            429,
            {
                "error": {
                    "message": "You exceeded your current quota.",
                    "code": "insufficient_quota",
                }
            },
            "quota",
        ),
        (
            ANTHROPIC,
            400,
            vendor_error("Your credit balance is too low to access the Anthropic API."),
            "quota",
        ),
        (
            AZURE,
            400,
            {"error": {"code": "BadRequest", "message": "API version not supported"}},
            "bad_request",
        ),
        (ANTHROPIC, 529, vendor_error("Overloaded", "overloaded_error"), "vendor_error"),
    ],
)
async def test_failures_are_told_apart(
    vendor: FakeVendor, model: str, status: int, body: dict, outcome: str
) -> None:
    vendor.reply(body, status=status)

    result = await check_connection(_connection(model, vendor), timeout=5)

    assert result.outcome == outcome, result.detail
    assert result.ok is (outcome == "ok")
    assert len(vendor.requests) == 1  # no retries: a check is a single call
    if not result.ok:
        assert result.detail


async def test_a_vendor_that_does_not_answer_in_time(vendor: FakeVendor) -> None:
    vendor.reply(openai_reply("OK"), delay=3)
    result = await check_connection(_connection(OPENAI, vendor), timeout=1)
    assert result.outcome is CheckOutcome.TIMEOUT
    assert result.latency_ms < 3000


@pytest.mark.parametrize("model", [OPENAI, ANTHROPIC, AZURE])
async def test_a_vendor_that_cannot_be_reached(model: str) -> None:
    closed = LlmConnection(model, model, KEY, api_base="http://127.0.0.1:9")
    if model == AZURE:
        closed = LlmConnection(model, model, KEY, "http://127.0.0.1:9", {"api_version": "v"})
    result = await check_connection(closed, timeout=3)
    assert result.outcome is CheckOutcome.UNREACHABLE


async def test_the_key_never_shows_in_the_detail(vendor: FakeVendor) -> None:
    # A vendor echoing the key (whole, or its beginning / end) back in its error
    vendor.reply(
        vendor_error(f"Key {KEY} rejected ({KEY[:8]}… / …{KEY[-8:]})", "authentication_error"),
        status=401,
    )
    result = await check_connection(_connection(ANTHROPIC, vendor), timeout=5)
    assert result.outcome is CheckOutcome.AUTH
    assert result.detail is not None
    assert KEY not in result.detail
    assert KEY[:8] not in result.detail and KEY[-8:] not in result.detail
    assert "***" in result.detail


# -- the endpoint ---------------------------------------------------------------------------


@pytest.fixture
def checks(monkeypatch) -> list[LlmConnection]:
    """Replace the vendor call: record the connections the endpoint would check."""
    seen: list[LlmConnection] = []

    async def fake_check(connection: LlmConnection, *, timeout: float) -> ConnectionCheck:
        seen.append(connection)
        return ConnectionCheck(CheckOutcome.OK, 42)

    monkeypatch.setattr(ai_router_module, "check_connection", fake_check)
    return seen


async def _model(client: AsyncClient, provider: str) -> str:
    return (await client.get(f"/api/ai-settings/providers/{provider}/models")).json()[0]["id"]


async def test_unsaved_settings_can_be_tested(
    tenant_client: AsyncClient, checks: list[LlmConnection], session: AsyncSession
) -> None:
    model = await _model(tenant_client, "anthropic")

    response = await tenant_client.post(
        "/api/ai-settings/test", json={"provider": "anthropic", "model": model, "apiKey": KEY}
    )

    assert response.status_code == 200, response.text
    assert response.json() == {"ok": True, "outcome": "ok", "detail": None, "latencyMs": 42}
    [connection] = checks
    assert (connection.model, connection.api_key, connection.api_base) == (
        f"anthropic/{model}",
        KEY,
        None,
    )
    # Testing stores nothing
    assert await session.scalar(select(AiSettings)) is None


async def test_the_stored_key_is_used_when_left_out(
    tenant_client: AsyncClient, checks: list[LlmConnection]
) -> None:
    first, second = [
        m["id"]
        for m in (await tenant_client.get("/api/ai-settings/providers/anthropic/models")).json()[:2]
    ]
    await tenant_client.put(
        "/api/ai-settings", json={"provider": "anthropic", "model": first, "apiKey": KEY}
    )

    # Trying another model with the stored key, before saving it
    response = await tenant_client.post(
        "/api/ai-settings/test", json={"provider": "anthropic", "model": second}
    )

    assert response.status_code == 200, response.text
    assert (checks[0].model, checks[0].api_key) == (f"anthropic/{second}", KEY)
    # ... but not with another provider: its key is needed
    response = await tenant_client.post(
        "/api/ai-settings/test",
        json={"provider": "openai", "model": await _model(tenant_client, "openai")},
    )
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "apiKey"]
    assert len(checks) == 1


async def test_settings_are_validated_before_testing(
    tenant_client: AsyncClient, checks: list[LlmConnection]
) -> None:
    for payload in (
        {"provider": "anthropic", "model": await _model(tenant_client, "anthropic")},  # no key
        {"provider": "anthropic", "model": "gpt-4o", "apiKey": KEY},
        {"provider": "ollama", "model": "llama3.1", "apiKey": KEY},
        {  # an endpoint that is not Azure's: never called
            "provider": "azure",
            "model": await _model(tenant_client, "azure"),
            "apiKey": KEY,
            "endpoint": "https://169.254.169.254",
        },
    ):
        response = await tenant_client.post("/api/ai-settings/test", json=payload)
        assert response.status_code == 422, payload
    assert checks == []


async def test_azure_and_bedrock_are_tested_with_their_fields(
    tenant_client: AsyncClient, checks: list[LlmConnection]
) -> None:
    azure_model = await _model(tenant_client, "azure")
    await tenant_client.post(
        "/api/ai-settings/test",
        json={
            "provider": "azure",
            "model": azure_model,
            "apiKey": KEY,
            "endpoint": "https://acme.openai.azure.com/",
            "deployment": "invoices-prod",
            "apiVersion": "2024-10-21",
        },
    )
    bedrock_model = await _model(tenant_client, "bedrock")
    await tenant_client.post(
        "/api/ai-settings/test",
        json={"provider": "bedrock", "model": bedrock_model, "apiKey": KEY, "region": "eu-west-1"},
    )

    azure, bedrock = checks
    assert (azure.model, azure.catalog_model, azure.api_base, azure.params) == (
        "azure/invoices-prod",
        f"azure/{azure_model}",
        "https://acme.openai.azure.com",
        {"api_version": "2024-10-21"},
    )
    assert (bedrock.model, bedrock.params) == (
        f"bedrock/{bedrock_model}",
        {"aws_region_name": "eu-west-1"},
    )


async def test_a_failed_check_is_reported_not_raised(
    tenant_client: AsyncClient, vendor: FakeVendor, monkeypatch
) -> None:
    """Through the whole stack: the endpoint, LiteLLM and a vendor rejecting the key."""
    real_build = ai_router_module.build_connection

    def to_the_fake_vendor(**fields: Any) -> LlmConnection:
        connection = real_build(**fields)
        return LlmConnection(connection.model, connection.catalog_model, connection.api_key,
                             api_base=vendor.url)  # fmt: skip

    monkeypatch.setattr(ai_router_module, "build_connection", to_the_fake_vendor)
    vendor.reply(vendor_error(f"invalid x-api-key {KEY}", "authentication_error"), status=401)

    response = await tenant_client.post(
        "/api/ai-settings/test",
        json={
            "provider": "anthropic",
            "model": await _model(tenant_client, "anthropic"),
            "apiKey": KEY,
        },  # fmt: skip
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["ok"], body["outcome"]) == (False, "auth")
    assert "invalid x-api-key" in body["detail"]
    assert KEY not in response.text
    assert vendor.requests[0][1]["x-api-key"] == KEY


async def test_only_tenants_test_ai_settings(
    client: AsyncClient, super_admin_client: AsyncClient, checks: list[LlmConnection]
) -> None:
    payload = {"provider": "openai", "model": "gpt-4o", "apiKey": KEY}
    assert (await client.post("/api/ai-settings/test", json=payload)).status_code == 401
    assert (await super_admin_client.post("/api/ai-settings/test", json=payload)).status_code == 403
    assert checks == []


async def test_saving_re_encrypts_the_stored_key(
    tenant_client: AsyncClient, session: AsyncSession
) -> None:
    """Saving without a key keeps the same key (under a fresh encryption)."""
    model = await _model(tenant_client, "gemini")
    await tenant_client.put(
        "/api/ai-settings", json={"provider": "gemini", "model": model, "apiKey": KEY}
    )
    before = (await session.scalar(select(AiSettings))).api_key_encrypted
    await tenant_client.put("/api/ai-settings", json={"provider": "gemini", "model": model})
    stored = await session.scalar(select(AiSettings))
    await session.refresh(stored)
    assert get_secret_box().decrypt(stored.api_key_encrypted) == KEY
    assert stored.api_key_encrypted != before
