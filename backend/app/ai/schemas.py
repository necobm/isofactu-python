"""Pydantic schemas of the AI module (API contract, camelCase JSON).

The API key is write-only: it is accepted on `PUT` and never returned -- reads only tell its
last four characters, so the user can recognise which key is set.
"""

import re
from datetime import datetime
from typing import Self
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator

from app.ai.providers import PROVIDERS
from app.core.schemas import ApiModel

# Azure OpenAI / AI Foundry resource endpoints. Anything else is refused: the server calls
# this URL with the tenant's key, so it must not be pointed at arbitrary (internal) hosts.
AZURE_ENDPOINT_SUFFIXES = (
    ".openai.azure.com",
    ".cognitiveservices.azure.com",
    ".services.ai.azure.com",
)
_AZURE_API_VERSION = re.compile(r"^(\d{4}-\d{2}-\d{2}(-preview)?|v1|latest|preview)$")
_AZURE_DEPLOYMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
_AWS_REGION = re.compile(r"^[a-z]{2}(-gov|-iso[a-z]*)?-[a-z]+-\d{1,2}$")


class ProviderRead(ApiModel):
    id: str = Field(examples=["anthropic"])
    label: str = Field(examples=["Anthropic"])
    needs_endpoint: bool = Field(
        description="Azure: `endpoint` is required; `apiVersion` and `deployment` optional"
    )
    needs_region: bool = Field(description="Bedrock: `region` is required")


class ModelRead(ApiModel):
    id: str = Field(examples=["claude-sonnet-4-5"])
    reads_pdf: bool = Field(
        description="The PDF itself is sent to the model, so scanned invoices can be read too"
    )
    structured_output: bool


def _azure_endpoint(value: str) -> str:
    """``https://<resource>.openai.azure.com`` (normalised: scheme and host only)."""
    parts = urlsplit(value.strip())
    host = (parts.hostname or "").lower()
    if (
        parts.scheme != "https"
        or not host.endswith(AZURE_ENDPOINT_SUFFIXES)
        or parts.port not in (None, 443)
        or parts.username
        or parts.password
        or parts.path not in ("", "/")
        or parts.query
        or parts.fragment
    ):
        raise ValueError(
            "endpoint must be the https URL of an Azure OpenAI resource, "
            "e.g. https://my-resource.openai.azure.com"
        )
    return f"https://{host}"


class AiSettingsWrite(ApiModel):
    """The AI vendor used to read received invoices from PDF. ``apiKey`` may be left out to
    keep the one already stored (it is required the first time and when the provider
    changes). Only the fields the provider needs are kept; the others are emptied."""

    provider: str = Field(max_length=20, examples=["anthropic"])
    model: str = Field(min_length=1, max_length=200, examples=["claude-sonnet-4-5"])
    api_key: str | None = Field(
        default=None, max_length=4096, description="Write-only; omit to keep the stored one"
    )
    endpoint: str = Field(
        default="", max_length=255, examples=["https://my-resource.openai.azure.com"]
    )
    api_version: str = Field(default="", max_length=50, description="Azure; empty = default")
    deployment: str = Field(default="", max_length=100, description="Azure; empty = the model name")
    region: str = Field(default="", max_length=30, examples=["eu-west-1"])

    @field_validator("api_key")
    @classmethod
    def _check_api_key(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        if any(ch.isspace() for ch in value.strip()):
            raise ValueError("apiKey cannot contain blanks")
        return value.strip()

    @model_validator(mode="after")
    def _check_provider_fields(self) -> Self:
        provider = PROVIDERS.get(self.provider)
        if provider is None:
            raise ValueError(f"provider must be one of: {', '.join(PROVIDERS)}")
        if provider.needs_endpoint:
            if not self.endpoint:
                raise ValueError("endpoint is required for Azure OpenAI")
            self.endpoint = _azure_endpoint(self.endpoint)
            if self.api_version and not _AZURE_API_VERSION.match(self.api_version):
                raise ValueError("apiVersion must look like 2024-10-21 or 2025-01-01-preview")
            if self.deployment and not _AZURE_DEPLOYMENT.match(self.deployment):
                raise ValueError("deployment can only contain letters, digits, '.', '_' and '-'")
        else:
            self.endpoint = self.api_version = self.deployment = ""
        if provider.needs_region:
            if not _AWS_REGION.match(self.region):
                raise ValueError("region must be an AWS region, e.g. eu-west-1")
        else:
            self.region = ""
        return self


class AiSettingsRead(ApiModel):
    provider: str
    model: str
    endpoint: str
    api_version: str
    deployment: str
    region: str
    api_key_hint: str | None = Field(
        description="The last characters of the stored key (`…f3a9`), to recognise it; `null` "
        "for short keys or when it cannot be decrypted",
        examples=["…f3a9"],
    )
    api_key_readable: bool = Field(
        description="`false` when the stored key cannot be decrypted any more (the server's "
        "encryption keys changed): it must be entered again"
    )
    reads_pdf: bool = Field(
        description="Whether the model reads PDF files (scans included) or only their text"
    )
    updated_at: datetime
