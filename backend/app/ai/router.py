"""HTTP endpoints of the AI module: each tenant's AI vendor (`/api/ai-settings`).

Every endpoint requires a logged-in ADMIN (the tenant) and only touches its own settings.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.accounts.deps import CurrentTenant
from app.ai.models import AiSettings
from app.ai.providers import PROVIDERS, CatalogModel, models
from app.ai.repository import AiSettingsRepository
from app.ai.schemas import (
    AiSettingsRead,
    AiSettingsWrite,
    ConnectionCheckRead,
    ModelRead,
    ProviderRead,
)
from app.ai.service import build_connection, check_connection
from app.core.config import get_settings
from app.core.crypto import SecretDecryptionError, get_secret_box
from app.core.database import get_session

SessionDep = Annotated[AsyncSession, Depends(get_session)]
ai_router = APIRouter(prefix="/ai-settings", tags=["AI settings"])

# Keys shorter than this do not reveal their last characters
HINT_MIN_LENGTH = 12
# A connection check is a tiny request: no need to wait as long as for a whole invoice
CHECK_TIMEOUT_SECONDS = 30.0


async def _models(provider_id: str) -> tuple[CatalogModel, ...]:
    # The first call imports LiteLLM and reads its catalogue (a few seconds): off the loop
    return await run_in_threadpool(models, provider_id)


def _validation_error(field: str, message: str) -> HTTPException:
    return HTTPException(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        [{"loc": ["body", field], "msg": message, "type": "value_error"}],
    )


async def _read(settings: AiSettings) -> AiSettingsRead:
    try:
        key = get_secret_box().decrypt(settings.api_key_encrypted)
    except SecretDecryptionError:
        readable, hint = False, None
    else:
        readable, hint = True, (f"…{key[-4:]}" if len(key) >= HINT_MIN_LENGTH else None)
    model = next((m for m in await _models(settings.provider) if m.id == settings.model), None)
    return AiSettingsRead(
        provider=settings.provider,
        model=settings.model,
        endpoint=settings.endpoint,
        api_version=settings.api_version,
        deployment=settings.deployment,
        region=settings.region,
        api_key_hint=hint,
        api_key_readable=readable,
        reads_pdf=bool(model and model.reads_pdf),
        updated_at=settings.updated_at,
    )


def _stored_key(settings: AiSettings | None, payload: AiSettingsWrite) -> str | None:
    """The stored key, when it still applies to the payload: same vendor (and, on Azure,
    same resource: its keys belong to it), and the server can still decrypt it."""
    if settings is None or settings.provider != payload.provider:
        return None
    if settings.endpoint != payload.endpoint:
        return None
    try:
        return get_secret_box().decrypt(settings.api_key_encrypted)
    except SecretDecryptionError:
        return None


async def _check_model(payload: AiSettingsWrite) -> None:
    if payload.model not in {m.id for m in await _models(payload.provider)}:
        raise _validation_error("model", "model is not one of the provider's models")


def _api_key(settings: AiSettings | None, payload: AiSettingsWrite) -> str:
    """The key to use: the one in the payload, else the stored one if it still applies."""
    key = payload.api_key or _stored_key(settings, payload)
    if key is None:
        raise _validation_error("apiKey", "apiKey is required")
    return key


@ai_router.get(
    "/providers",
    response_model=list[ProviderRead],
    summary="AI vendors",
    description="The vendors a tenant can read its received invoices with.",
)
async def list_providers(tenant: CurrentTenant) -> list[ProviderRead]:
    return [
        ProviderRead(
            id=p.id, label=p.label, needs_endpoint=p.needs_endpoint, needs_region=p.needs_region
        )
        for p in PROVIDERS.values()
    ]


@ai_router.get(
    "/providers/{provider_id}/models",
    response_model=list[ModelRead],
    summary="Models of an AI vendor",
    description=(
        "The vendor's chat models known to the server (LiteLLM's model catalogue): those that "
        "read PDF files first -- they also read scanned invoices --, then those that only get "
        "the text of the PDF. `404` for an unknown vendor."
    ),
)
async def list_models(tenant: CurrentTenant, provider_id: str) -> list[ModelRead]:
    if provider_id not in PROVIDERS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown AI provider")
    return [
        ModelRead(id=m.id, reads_pdf=m.reads_pdf, structured_output=m.structured_output)
        for m in await _models(provider_id)
    ]


@ai_router.get(
    "",
    response_model=AiSettingsRead | None,
    summary="AI settings of the account",
    description=(
        "The vendor and model the account reads received invoices with, or `null` while it "
        "is not set up (PDF import is then unavailable). The API key is never returned."
    ),
)
async def get_ai_settings(tenant: CurrentTenant, session: SessionDep) -> AiSettingsRead | None:
    settings = await AiSettingsRepository(session, tenant.id).get()
    return None if settings is None else await _read(settings)


@ai_router.put(
    "",
    response_model=AiSettingsRead,
    summary="Set the AI settings of the account",
    description=(
        "Creates or replaces the AI settings. `model` must be one of the provider's models "
        "(`GET /api/ai-settings/providers/{provider}/models`). `apiKey` is stored encrypted; "
        "leave it out to keep the stored one -- it is required the first time, whenever the "
        "provider (or the Azure endpoint) changes, and when the stored one can no longer be "
        "decrypted."
    ),
)
async def put_ai_settings(
    tenant: CurrentTenant, payload: AiSettingsWrite, session: SessionDep
) -> AiSettingsRead:
    await _check_model(payload)
    repo = AiSettingsRepository(session, tenant.id)
    settings = await repo.get()
    encrypted = get_secret_box().encrypt(_api_key(settings, payload))
    fields = payload.model_dump(exclude={"api_key"})
    if settings is None:
        settings = await repo.add(AiSettings(owner=tenant, api_key_encrypted=encrypted, **fields))
    else:
        for name, value in fields.items():
            setattr(settings, name, value)
        settings.api_key_encrypted = encrypted
    await session.commit()
    await session.refresh(settings)
    return await _read(settings)


@ai_router.post(
    "/test",
    response_model=ConnectionCheckRead,
    summary="Test AI settings",
    description=(
        "Checks that the given settings work -- the key, the model and (Azure / Bedrock) the "
        "endpoint or region -- with a minimal request to the vendor, before or after saving "
        "them: the body is the same as for `PUT`, and nothing is stored. Without `apiKey` the "
        "stored key is used (under the same conditions as `PUT`). Answers `200` whatever the "
        "vendor says: `ok` and `outcome` tell how the check went. It is a real API call, "
        "billed to the key."
    ),
)
async def test_ai_settings(
    tenant: CurrentTenant, payload: AiSettingsWrite, session: SessionDep
) -> ConnectionCheckRead:
    await _check_model(payload)
    settings = await AiSettingsRepository(session, tenant.id).get()
    connection = build_connection(
        provider=payload.provider,
        model=payload.model,
        api_key=_api_key(settings, payload),
        endpoint=payload.endpoint,
        api_version=payload.api_version,
        deployment=payload.deployment,
        region=payload.region,
    )
    timeout = min(CHECK_TIMEOUT_SECONDS, get_settings().llm_timeout)
    result = await check_connection(connection, timeout=timeout)
    return ConnectionCheckRead(
        ok=result.ok, outcome=result.outcome, detail=result.detail, latency_ms=result.latency_ms
    )


@ai_router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove the AI settings of the account",
    description="Forgets the vendor, model and API key: PDF import becomes unavailable.",
)
async def delete_ai_settings(tenant: CurrentTenant, session: SessionDep) -> None:
    repo = AiSettingsRepository(session, tenant.id)
    settings = await repo.get()
    if settings is not None:
        await repo.delete(settings)
        await session.commit()
