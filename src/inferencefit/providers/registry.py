"""Central construction of the fixed built-in provider adapters."""

from __future__ import annotations

import warnings
from collections.abc import Callable
from pathlib import Path

from inferencefit.contracts import CandidateSpec
from inferencefit.credentials import EnvironmentCredentialResolver

from .anthropic import AnthropicProvider
from .base import ProviderAdapter
from .fixture import FixtureProvider
from .openai_compatible import PRESET_URLS, OpenAICompatibleProvider
from .openai_responses import OpenAIResponsesProvider
from .openrouter import OpenRouterProvider

_BUILDERS: dict[str, Callable[[str | None], ProviderAdapter]] = {
    "anthropic": AnthropicProvider,
    "claude": AnthropicProvider,
    "openrouter": OpenRouterProvider,
    "gemini": OpenAICompatibleProvider,
    "openai": OpenAIResponsesProvider,
}
_KNOWN_PROVIDERS = frozenset({*PRESET_URLS, *_BUILDERS, "fixture", "custom"})


def create_provider(
    candidate: CandidateSpec, *, spec_dir: Path, resolver: EnvironmentCredentialResolver
) -> ProviderAdapter:
    if candidate.provider == "fixture":
        return FixtureProvider(spec_dir)
    credential = resolver.resolve(candidate.credential_ref, candidate.provider)
    if candidate.provider == "custom":
        return OpenAICompatibleProvider(credential)
    if candidate.base_url:
        if candidate.provider not in _KNOWN_PROVIDERS:
            warnings.warn(
                "Unknown provider with base_url is deprecated; use provider: custom",
                UserWarning,
                stacklevel=2,
            )
        return OpenAICompatibleProvider(credential)
    builder = _BUILDERS.get(candidate.provider, OpenAICompatibleProvider)
    return builder(credential)
