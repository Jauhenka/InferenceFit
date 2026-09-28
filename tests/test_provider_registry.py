"""Fixed provider dispatch and compatibility precedence."""

import json

import httpx
import pytest

from inferencefit import providers
from inferencefit.contracts import CandidateSpec
from inferencefit.contracts import TestCase as Case
from inferencefit.credentials import EnvironmentCredentialResolver
from inferencefit.providers import (
    FixtureProvider,
    OpenAICompatibleProvider,
    OpenAIResponsesProvider,
    OpenRouterProvider,
    ProviderError,
)


class RecordingResolver(EnvironmentCredentialResolver):
    def __init__(self):
        self.calls = []

    def resolve(self, reference, provider):
        self.calls.append((reference, provider))
        return super().resolve(reference, provider)


@pytest.fixture
def create_provider():
    def create(*args, **kwargs):
        assert hasattr(providers, "create_provider"), "central provider factory must be exported"
        return providers.create_provider(*args, **kwargs)

    return create


def case():
    return Case.model_validate(
        {"id": "c", "request": {"messages": [{"role": "user", "content": "hello"}]}}
    )


@pytest.mark.asyncio
async def test_fixture_resolves_relative_file_from_spec_dir_without_credentials(
    tmp_path, create_provider
):
    (tmp_path / "responses.jsonl").write_text(
        json.dumps({"case_id": "c", "raw_output": "fixture answer"}) + "\n",
        encoding="utf-8",
    )
    candidate = CandidateSpec(
        id="fixture",
        provider="fixture",
        model="local",
        credential_ref="unavailable",
        parameters={"fixture_path": "responses.jsonl"},
    )
    resolver = RecordingResolver()
    adapter = create_provider(candidate, spec_dir=tmp_path, resolver=resolver)
    assert type(adapter) is FixtureProvider
    assert (await adapter.complete(candidate, case(), 0)).raw_output == "fixture answer"
    assert resolver.calls == []


@pytest.mark.parametrize(
    "provider,adapter_type",
    [
        ("openrouter", OpenRouterProvider),
        ("openai", OpenAIResponsesProvider),
        ("gemini", OpenAICompatibleProvider),
        ("fireworks", OpenAICompatibleProvider),
        ("deepseek", OpenAICompatibleProvider),
        ("ollama", OpenAICompatibleProvider),
        ("vllm", OpenAICompatibleProvider),
        ("custom", OpenAICompatibleProvider),
    ],
)
def test_dispatch_resolves_non_fixture_credential_exactly_once(
    provider, adapter_type, tmp_path, monkeypatch, create_provider
):
    monkeypatch.setenv("INFERENCEFIT_CREDENTIAL_REGISTRY", "registry-token")
    candidate = CandidateSpec(
        id="x",
        provider=provider,
        model="requested",
        credential_ref="registry",
        base_url="https://custom.test/v1" if provider == "custom" else None,
    )
    resolver = RecordingResolver()
    adapter = create_provider(candidate, spec_dir=tmp_path, resolver=resolver)
    assert type(adapter) is adapter_type
    assert adapter.credential == "registry-token"
    assert resolver.calls == [("registry", provider)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider,url",
    [
        ("gemini", "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"),
        ("fireworks", "https://api.fireworks.ai/inference/v1/chat/completions"),
        ("deepseek", "https://api.deepseek.com/chat/completions"),
        ("ollama", "http://127.0.0.1:11434/v1/chat/completions"),
        ("vllm", "http://127.0.0.1:8000/v1/chat/completions"),
    ],
)
async def test_generic_profiles_keep_existing_chat_endpoints(
    provider, url, tmp_path, monkeypatch, respx_mock, create_provider
):
    monkeypatch.setenv("INFERENCEFIT_CREDENTIAL_REGISTRY", "registry-token")
    respx_mock.post(url).mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "profile answer"}}],
            },
        )
    )
    candidate = CandidateSpec(
        id="x", provider=provider, model="requested", credential_ref="registry"
    )
    adapter = create_provider(candidate, spec_dir=tmp_path, resolver=RecordingResolver())
    assert (await adapter.complete(candidate, case(), 0)).raw_output == "profile answer"


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["openrouter", "gemini", "openai", "custom"])
async def test_explicit_base_url_forces_generic_chat_path(
    provider, tmp_path, monkeypatch, respx_mock, create_provider
):
    monkeypatch.setenv("INFERENCEFIT_CREDENTIAL_REGISTRY", "registry-token")
    route = respx_mock.post("https://custom.test/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "custom answer"}}],
                "provider": "ignored-backend",
                "usage": {"cost": 9},
            },
        )
    )
    candidate = CandidateSpec(
        id="x",
        provider=provider,
        model="requested",
        credential_ref="registry",
        base_url="https://custom.test/v1",
    )
    resolver = RecordingResolver()
    adapter = create_provider(candidate, spec_dir=tmp_path, resolver=resolver)
    assert type(adapter) is OpenAICompatibleProvider
    response = await adapter.complete(candidate, case(), 0)
    assert response.raw_output == "custom answer"
    assert response.cost_usd is response.provider_backend is None
    assert "X-OpenRouter-Metadata" not in route.calls[0].request.headers
    assert resolver.calls == [("registry", provider)]


@pytest.mark.asyncio
async def test_unknown_provider_without_base_url_fails_at_request_time(tmp_path, create_provider):
    candidate = CandidateSpec(id="x", provider="unknown", model="requested")
    resolver = RecordingResolver()
    adapter = create_provider(candidate, spec_dir=tmp_path, resolver=resolver)
    assert type(adapter) is OpenAICompatibleProvider
    assert resolver.calls == [(None, "unknown")]
    with pytest.raises(ProviderError, match="requires base_url"):
        await adapter.complete(candidate, case(), 0)
