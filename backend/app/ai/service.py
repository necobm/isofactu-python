"""From a tenant's stored AI settings to what LiteLLM needs to call the vendor."""

from dataclasses import dataclass, field
from typing import Any

from app.ai.models import AiSettings
from app.core.crypto import SecretBox


@dataclass(frozen=True, slots=True)
class LlmConnection:
    # The model as LiteLLM calls it: `provider/model` (`azure/<deployment>` on Azure)
    model: str
    # The model as LiteLLM's catalogue knows it, to look up what it can do: on Azure the
    # deployment may have any name, but it runs one of the catalogue's models
    catalog_model: str
    api_key: str = field(repr=False)
    api_base: str | None = None
    # Vendor-specific parameters (`api_version` on Azure, `aws_region_name` on Bedrock)
    params: dict[str, Any] = field(default_factory=dict)


def connection_for(settings: AiSettings, box: SecretBox) -> LlmConnection:
    """Raises ``SecretDecryptionError`` when the stored key cannot be decrypted.

    The tenant's own key is always passed explicitly, so LiteLLM never falls back to vendor
    credentials it could find in the server's environment (``OPENAI_API_KEY``...)."""
    api_key = box.decrypt(settings.api_key_encrypted)
    catalog_model = f"{settings.provider}/{settings.model}"
    if settings.provider == "azure":
        params = {"api_version": settings.api_version} if settings.api_version else {}
        return LlmConnection(
            model=f"azure/{settings.deployment or settings.model}",
            catalog_model=catalog_model,
            api_key=api_key,
            api_base=settings.endpoint,
            params=params,
        )
    if settings.provider == "bedrock":
        return LlmConnection(
            catalog_model,
            catalog_model,
            api_key,
            params={"aws_region_name": settings.region},
        )
    return LlmConnection(catalog_model, catalog_model, api_key)
