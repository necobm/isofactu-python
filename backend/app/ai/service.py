"""From a tenant's AI settings to what LiteLLM needs to call the vendor, and a quick check
that those settings work ("Probar conexión")."""

import logging
import re
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.ai.models import AiSettings
from app.ai.providers import import_litellm
from app.core.crypto import SecretBox

logger = logging.getLogger(__name__)


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


def build_connection(
    *,
    provider: str,
    model: str,
    api_key: str,
    endpoint: str = "",
    api_version: str = "",
    deployment: str = "",
    region: str = "",
) -> LlmConnection:
    """What LiteLLM needs to call the vendor with these settings.

    The tenant's own key is always passed explicitly, so LiteLLM never falls back to vendor
    credentials it could find in the server's environment (``OPENAI_API_KEY``...)."""
    catalog_model = f"{provider}/{model}"
    if provider == "azure":
        params = {"api_version": api_version} if api_version else {}
        return LlmConnection(
            model=f"azure/{deployment or model}",
            catalog_model=catalog_model,
            api_key=api_key,
            api_base=endpoint,
            params=params,
        )
    if provider == "bedrock":
        return LlmConnection(
            catalog_model, catalog_model, api_key, params={"aws_region_name": region}
        )
    return LlmConnection(catalog_model, catalog_model, api_key)


def connection_for(settings: AiSettings, box: SecretBox) -> LlmConnection:
    """The connection of a tenant's stored settings. Raises ``SecretDecryptionError`` when
    the stored key cannot be decrypted."""
    return build_connection(
        provider=settings.provider,
        model=settings.model,
        api_key=box.decrypt(settings.api_key_encrypted),
        endpoint=settings.endpoint,
        api_version=settings.api_version,
        deployment=settings.deployment,
        region=settings.region,
    )


# -- checking a connection ------------------------------------------------------------------


class CheckOutcome(StrEnum):
    """How a connection check ended."""

    OK = "ok"
    AUTH = "auth"  # the vendor rejected the key
    PERMISSION = "permission"  # the key is valid but may not use this model / resource
    MODEL = "model"  # no such model (or deployment) for this key
    QUOTA = "quota"  # rate limit or no credit left
    TIMEOUT = "timeout"
    UNREACHABLE = "unreachable"  # the vendor's endpoint could not be reached
    BAD_REQUEST = "bad_request"  # the vendor refused the request (API version, region...)
    VENDOR_ERROR = "vendor_error"  # anything else: the vendor failed


@dataclass(frozen=True, slots=True)
class ConnectionCheck:
    outcome: CheckOutcome
    latency_ms: int
    # The vendor's explanation, with the key scrubbed out; None on success
    detail: str | None = None

    @property
    def ok(self) -> bool:
        return self.outcome is CheckOutcome.OK


# The smallest useful request: any answer proves the key, the model and the endpoint work
_PING = [{"role": "user", "content": "Reply with the single word OK."}]
_PING_MAX_TOKENS = 16
_DETAIL_LIMIT = 300
# What vendors say in the messages LiteLLM does not map to a precise exception
_CREDENTIAL = r"(api[ _-]?key|security token|token|credentials?|subscription key)"
_BAD = r"(invalid|not valid|incorrect|expired|revoked)"
_INVALID_CREDENTIALS = re.compile(
    rf"{_CREDENTIAL}\b[^.]*\b{_BAD}|{_BAD}\b[^.]*\b{_CREDENTIAL}", re.IGNORECASE
)
_QUOTA = re.compile(r"credit|quota|billing|balance|insufficient[ _-]funds", re.IGNORECASE)
_MODEL = re.compile(r"model|deployment", re.IGNORECASE)
_MISSING = re.compile(r"not[ _-]?found|does not exist|unknown|invalid|not supported", re.I)
_CONNECTION = re.compile(
    r"connection error|cannot connect|connect call failed|connection refused|"
    r"name or service not known|nodename nor servname|getaddrinfo|name resolution",
    re.IGNORECASE,
)


def _scrub(message: str, secret: str) -> str:
    """The vendor's message, safe to show: without the key (or a long part of it), on one
    line and bounded."""
    if secret:
        message = message.replace(secret, "***")
        if len(secret) >= 12:
            message = message.replace(secret[:8], "***").replace(secret[-8:], "***")
    message = " ".join(message.split())
    return message[:_DETAIL_LIMIT] + ("…" if len(message) > _DETAIL_LIMIT else "")


def classify_error(exc: BaseException) -> CheckOutcome:
    """The outcome LiteLLM's exception stands for. Vendors disagree on status codes (a key
    without access to a model is a 403 on Anthropic, a credit problem a 400...) and LiteLLM
    reports some network failures as server errors, so the message is looked at too."""
    litellm = import_litellm()
    message = str(exc)
    # Order matters: Timeout is an APIConnectionError, ContextWindowExceeded a BadRequest
    if isinstance(exc, litellm.AuthenticationError):
        return CheckOutcome.AUTH
    if isinstance(exc, litellm.PermissionDeniedError):
        return (
            CheckOutcome.AUTH if _INVALID_CREDENTIALS.search(message) else CheckOutcome.PERMISSION
        )
    if isinstance(exc, litellm.NotFoundError):
        return CheckOutcome.MODEL
    if isinstance(exc, litellm.RateLimitError):
        return CheckOutcome.QUOTA
    if isinstance(exc, litellm.Timeout):
        return CheckOutcome.TIMEOUT
    if isinstance(exc, litellm.APIConnectionError):
        return CheckOutcome.UNREACHABLE
    if isinstance(exc, litellm.BadRequestError):
        if _INVALID_CREDENTIALS.search(message):
            return CheckOutcome.AUTH
        if _QUOTA.search(message):
            return CheckOutcome.QUOTA
        if _MODEL.search(message) and _MISSING.search(message):
            return CheckOutcome.MODEL
        return CheckOutcome.BAD_REQUEST
    if _CONNECTION.search(message):
        return CheckOutcome.UNREACHABLE
    return CheckOutcome.VENDOR_ERROR


async def check_connection(connection: LlmConnection, *, timeout: float) -> ConnectionCheck:
    """Send the vendor a minimal request with these settings. Never raises: whatever goes
    wrong is reported as the check's outcome. The request is a real (tiny) API call, billed
    to the tenant's key."""
    litellm = import_litellm()
    started = time.perf_counter()

    def elapsed() -> int:
        return round((time.perf_counter() - started) * 1000)

    try:
        await litellm.acompletion(
            model=connection.model,
            messages=_PING,
            max_tokens=_PING_MAX_TOKENS,
            timeout=timeout,
            num_retries=0,
            api_key=connection.api_key,
            api_base=connection.api_base,
            drop_params=True,
            **connection.params,
        )
    except Exception as exc:  # noqa: BLE001 -- LiteLLM raises a different class per vendor
        outcome = classify_error(exc)
        logger.info("AI connection check with %s failed: %s", connection.model, outcome.value)
        return ConnectionCheck(outcome, elapsed(), _scrub(str(exc), connection.api_key))
    return ConnectionCheck(CheckOutcome.OK, elapsed())
