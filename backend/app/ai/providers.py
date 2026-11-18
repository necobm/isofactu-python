"""The AI vendors a tenant can choose from, and the models each one offers.

Invoices are read through LiteLLM, so the model lists come from the model catalogue bundled
with it (``litellm.model_cost``): no API key or network access is needed to list them, and
the catalogue also says what each model can do -- whether it reads PDF files (needed for
scanned invoices) and whether it supports structured output. The lists follow the LiteLLM
version installed: upgrading it brings newer models.

Only chat models are offered, without deprecated ones, fine-tuning templates, region-pinned
duplicates (``azure/eu/...``, ``bedrock/us-east-1/...``) or special-purpose variants (search,
audio, realtime, computer use...). Bedrock's cross-region inference profiles (``eu.``, ``us.``...)
are kept: they are how newer models are called, and ``eu.`` keeps the data in the EU.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import date
from functools import cache
from typing import Any


@dataclass(frozen=True, slots=True)
class Provider:
    id: str
    label: str
    # LiteLLM `litellm_provider` values whose catalogue entries are this vendor's models
    catalog: tuple[str, ...]
    # Extra, non-secret settings the vendor needs besides model and API key
    needs_endpoint: bool = False  # Azure: the resource endpoint, API version, deployment
    needs_region: bool = False  # Bedrock: the AWS region


PROVIDERS: dict[str, Provider] = {
    provider.id: provider
    for provider in (
        Provider("gemini", "Google Gemini", ("gemini",)),
        Provider("anthropic", "Anthropic", ("anthropic",)),
        Provider("openai", "OpenAI", ("openai",)),
        Provider("azure", "Azure OpenAI", ("azure",), needs_endpoint=True),
        Provider("bedrock", "Amazon Bedrock", ("bedrock", "bedrock_converse"), needs_region=True),
    )
}


@dataclass(frozen=True, slots=True)
class CatalogModel:
    id: str  # as the tenant picks it and LiteLLM expects it after `provider/`
    reads_pdf: bool  # the PDF itself is sent: scans work too
    structured_output: bool  # the answer format (JSON schema) is enforced by the vendor


def import_litellm() -> Any:
    """Import LiteLLM (slow: only when first needed) without it fetching its model
    catalogue from GitHub at run time: the copy bundled with the package is used, so the
    model lists are stable for a given installation. Set those variables to ``False`` in the
    environment to get the live data back."""
    os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    os.environ.setdefault("LITELLM_LOCAL_ANTHROPIC_BETA_HEADERS", "True")
    import litellm

    litellm.suppress_debug_info = True
    return litellm


# Variants that are not general chat models, or not meant for this job
_UNSUITABLE = re.compile(
    r"ft:|search|computer-use|audio|realtime|tts|transcri|image|embed|robotics|"
    r"deep-research|customtools|container|moderation|lyria",
    re.IGNORECASE,
)


def _model_id(name: str, provider: Provider) -> str | None:
    """The catalogue entry ``name`` as a model id of the provider (without the provider
    prefix), or None for entries that are not offered."""
    for prefix in {*provider.catalog, provider.id}:
        if name.startswith(f"{prefix}/"):
            name = name[len(prefix) + 1 :]
            break
    if "/" in name or _UNSUITABLE.search(name):
        return None  # region-pinned duplicates, routing variants, special-purpose models
    return name


def _is_deprecated(info: dict[str, Any], today: date) -> bool:
    deprecation = info.get("deprecation_date")
    if not isinstance(deprecation, str):
        return False
    try:
        return date.fromisoformat(deprecation[:10]) <= today
    except ValueError:
        return False


def _natural_key(model_id: str) -> list[Any]:
    """``gpt-4.1`` before ``gpt-4o`` before ``gpt-10``: numbers compare as numbers."""
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", model_id)]


def catalog_models(
    provider: Provider, catalog: dict[str, dict[str, Any]], today: date
) -> tuple[CatalogModel, ...]:
    """The models of ``provider`` in the LiteLLM ``catalog``: those that read PDF files
    first (they handle every invoice, scans included), then the rest; newest-looking first
    within each group."""
    found: dict[str, CatalogModel] = {}
    for name, info in catalog.items():
        if not isinstance(info, dict) or info.get("litellm_provider") not in provider.catalog:
            continue
        if info.get("mode") != "chat" or _is_deprecated(info, today):
            continue
        model_id = _model_id(name, provider)
        if model_id is None:
            continue
        known = found.get(model_id)
        found[model_id] = CatalogModel(
            model_id,
            reads_pdf=bool(info.get("supports_pdf_input")) or bool(known and known.reads_pdf),
            structured_output=bool(info.get("supports_response_schema"))
            or bool(known and known.structured_output),
        )
    newest_first = sorted(found.values(), key=lambda m: _natural_key(m.id), reverse=True)
    return tuple(sorted(newest_first, key=lambda m: not m.reads_pdf))  # stable


@cache
def models(provider_id: str) -> tuple[CatalogModel, ...]:
    """The models a tenant can pick for the provider (empty for unknown providers)."""
    provider = PROVIDERS.get(provider_id)
    if provider is None:
        return ()
    return catalog_models(provider, import_litellm().model_cost, date.today())


def find_model(provider_id: str, model_id: str) -> CatalogModel | None:
    return next((m for m in models(provider_id) if m.id == model_id), None)
