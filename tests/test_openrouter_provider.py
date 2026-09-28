"""Offline OpenRouter boundary, metadata, and credential contracts."""

import json

import httpx
import pytest

from inferencefit import providers
from inferencefit.contracts import CandidateSpec
from inferencefit.contracts import TestCase as Case
from inferencefit.credentials import EnvironmentCredentialResolver
from inferencefit.errors import MissingCredentialError
from inferencefit.providers import ProviderError

URL = "https://openrouter.ai/api/v1/chat/completions"


@pytest.fixture
def adapter():
    def create():
        assert hasattr(providers, "OpenRouterProvider"), "OpenRouter adapter must be exported"
        return providers.OpenRouterProvider("secret-token")

    return create


def candidate():
    return CandidateSpec(
        id="router",
        provider="openrouter",
        model="vendor/native-model",
        parameters={"temperature": 0.3, "provider": {"order": ["Example"]}},
    )


def case():
    return Case.model_validate(
        {"id": "c", "request": {"messages": [{"role": "user", "content": "hello"}]}}
    )


def body(**metadata):
    return {"choices": [{"message": {"content": "answer"}}], **metadata}


@pytest.mark.asyncio
async def test_native_request_and_reported_metadata(adapter, respx_mock):
    route = respx_mock.post(URL).mock(
        return_value=httpx.Response(
            200,
            json=body(
                model="vendor/actual-model",
                provider="Example",
                usage={
                    "prompt_tokens": 2,
                    "completion_tokens": 3,
                    "total_tokens": 5,
                    "cost": 0.0012,
                },
            ),
        )
    )
    result = await adapter().complete(candidate(), case(), 0)
    request = route.calls[0].request
    assert request.headers["Authorization"] == "Bearer secret-token"
    assert request.headers["X-OpenRouter-Metadata"] == "enabled"
    assert json.loads(request.content) == {
        "model": "vendor/native-model",
        "messages": [{"role": "user", "content": "hello"}],
        "temperature": 0.3,
        "provider": {"order": ["Example"]},
    }
    assert result.raw_output == "answer"
    assert (result.input_tokens, result.output_tokens, result.total_tokens) == (2, 3, 5)
    assert (result.provider, result.model, result.provider_backend) == (
        "openrouter",
        "vendor/actual-model",
        "Example",
    )
    assert result.cost_usd == 0.0012


@pytest.mark.asyncio
@pytest.mark.parametrize("cost", [0, 0.0, 0.25])
async def test_reported_cost_including_zero_is_preserved(adapter, respx_mock, cost):
    respx_mock.post(URL).mock(return_value=httpx.Response(200, json=body(usage={"cost": cost})))
    assert (await adapter().complete(candidate(), case(), 0)).cost_usd == cost


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "metadata",
    [
        {},
        {"usage": None, "provider": None, "model": None},
        {"usage": [], "provider": {}, "model": []},
        {
            "usage": {
                "cost": "bad",
                "prompt_tokens": "bad",
                "completion_tokens": -1,
                "total_tokens": [],
            },
            "provider": "",
        },
        *[{"usage": {"cost": cost}} for cost in [True, -1, float("inf"), float("nan"), {}]],
    ],
)
async def test_optional_metadata_never_breaks_text(adapter, respx_mock, metadata):
    # JSON containing NaN is accepted by Python's decoder, allowing defensive coverage.
    respx_mock.post(URL).mock(return_value=httpx.Response(200, text=json.dumps(body(**metadata))))
    result = await adapter().complete(candidate(), case(), 0)
    assert result.raw_output == "answer"
    assert result.model == "vendor/native-model"
    assert result.cost_usd is result.provider_backend is None
    assert result.input_tokens is result.output_tokens is result.total_tokens is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response", ["invalid-json", "{}", '{"choices": []}', '{"choices": [{"message": {}}]}']
)
async def test_malformed_responses_are_safe(adapter, respx_mock, response):
    respx_mock.post(URL).mock(return_value=httpx.Response(200, text=response))
    with pytest.raises(ProviderError) as caught:
        await adapter().complete(candidate(), case(), 0)
    assert caught.value.kind == "response"
    assert caught.value.retryable is False
    assert "secret-token" not in str(caught.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,kind,retryable",
    [
        (401, "authentication", False),
        (403, "permission", False),
        (429, "rate_limit", True),
        (503, "server", True),
    ],
)
async def test_http_errors_are_classified_and_redacted(
    adapter, respx_mock, status, kind, retryable
):
    respx_mock.post(URL).mock(return_value=httpx.Response(status, text="secret-token body-secret"))
    with pytest.raises(ProviderError) as caught:
        await adapter().complete(candidate(), case(), 0)
    assert (caught.value.kind, caught.value.retryable) == (kind, retryable)
    assert "secret-token" not in str(caught.value)
    assert "body-secret" not in str(caught.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exception,kind", [(httpx.ReadTimeout, "timeout"), (httpx.ConnectError, "network")]
)
async def test_transport_errors_are_safe_and_retryable(adapter, respx_mock, exception, kind):
    respx_mock.post(URL).mock(side_effect=exception("secret-token"))
    with pytest.raises(ProviderError) as caught:
        await adapter().complete(candidate(), case(), 0)
    assert (caught.value.kind, caught.value.retryable) == (kind, True)
    assert "secret-token" not in str(caught.value)


def test_exact_open_router_credential_fallback(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("OPEN_ROUTER_API_KEY", "required-token")
    assert EnvironmentCredentialResolver().resolve(None, "openrouter") == "required-token"


def test_legacy_credential_spelling_is_not_accepted(monkeypatch):
    monkeypatch.delenv("OPEN_ROUTER_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "legacy-token")
    with pytest.raises(MissingCredentialError) as caught:
        EnvironmentCredentialResolver().resolve(None, "openrouter")
    assert "legacy-token" not in str(caught.value)
