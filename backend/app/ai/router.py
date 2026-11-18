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
from app.ai.schemas import AiSettingsRead, AiSettingsWrite, ModelRead, ProviderRead
from app.core.crypto import SecretDecryptionError, get_secret_box
from app.core.database import get_session

SessionDep = Annotated[AsyncSession, Depends(get_session)]
ai_router = APIRouter(prefix="/ai-settings", tags=["AI settings"])

# Keys shorter than this do not reveal their last characters
HINT_MIN_LENGTH = 12


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


def _can_keep_key(settings: AiSettings | None, payload: AiSettingsWrite) -> bool:
    """Whether the stored key still applies: same vendor (and, on Azure, same resource:
    its keys belong to it), and the server can still decrypt it."""
    if settings is None or settings.provider != payload.provider:
        return False
    if settings.endpoint != payload.endpoint:
        return False
    try:
        get_secret_box().decrypt(settings.api_key_encrypted)
    except SecretDecryptionError:
        return False
    return True


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
    if payload.model not in {m.id for m in await _models(payload.provider)}:
        raise _validation_error("model", "model is not one of the provider's models")

    repo = AiSettingsRepository(session, tenant.id)
    settings = await repo.get()
    if payload.api_key is not None:
        encrypted = get_secret_box().encrypt(payload.api_key)
    elif _can_keep_key(settings, payload):
        encrypted = settings.api_key_encrypted  # type: ignore[union-attr] -- checked
    else:
        raise _validation_error("apiKey", "apiKey is required")
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
