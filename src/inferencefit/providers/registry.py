"""Central construction of the fixed built-in provider adapters."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from inferencefit.contracts import CandidateSpec
from inferencefit.credentials import EnvironmentCredentialResolver

from .base import ProviderAdapter
from .fixture import FixtureProvider
from .openai_compatible import OpenAICompatibleProvider
from .openai_responses import OpenAIResponsesProvider
from .openrouter import OpenRouterProvider

_BUILDERS: dict[str, Callable[[str | None], ProviderAdapter]] = {
    "openrouter": OpenRouterProvider,
    "gemini": OpenAICompatibleProvider,
    "openai": OpenAIResponsesProvider,
}


def create_provider(
    candidate: CandidateSpec, *, spec_dir: Path, resolver: EnvironmentCredentialResolver
) -> ProviderAdapter:
    if candidate.provider == "fixture":
        return FixtureProvider(spec_dir)
    credential = resolver.resolve(candidate.credential_ref, candidate.provider)
    if candidate.base_url:
        return OpenAICompatibleProvider(credential)
    builder = _BUILDERS.get(candidate.provider, OpenAICompatibleProvider)
    return builder(credential)
