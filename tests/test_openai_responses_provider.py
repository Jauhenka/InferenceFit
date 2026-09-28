"""Offline native OpenAI Responses boundary and normalization contracts."""

import json

import httpx
import pytest

from inferencefit import providers
from inferencefit.contracts import CandidateSpec
from inferencefit.contracts import TestCase as Case
from inferencefit.credentials import EnvironmentCredentialResolver
from inferencefit.errors import MissingCredentialError
from inferencefit.providers import ProviderError

URL = "https://api.openai.com/v1/responses"


@pytest.fixture
def adapter():
    def create():
        assert hasattr(providers, "OpenAIResponsesProvider"), "Responses adapter must be exported"
        return providers.OpenAIResponsesProvider("secret-token")

    return create


def candidate(parameters=None):
    return CandidateSpec(
        id="openai",
        provider="openai",
        model="gpt-native-model",
        base_url="https://ignored.test",
        parameters=parameters or {},
    )


def case():
    return Case.model_validate(
        {
            "id": "c",
            "request": {
                "messages": [
                    {"role": "system", "content": "Be brief."},
                    {"role": "user", "content": "hello"},
                ]
            },
        }
    )


def body(**metadata):
    return {
        "id": "resp_example",
        "object": "response",
        "status": "completed",
        "model": "gpt-actual-model",
        "output": [
            {"type": "reasoning", "summary": []},
            {"type": "function_call", "name": "ignored", "arguments": "{}"},
            {
                "type": "message",
                "role": "assistant",
                "content": [
                    {"type": "output_text", "text": "first", "annotations": []},
                    {"type": "refusal", "refusal": "ignored"},
                    {"type": "output_text", "text": " second", "annotations": []},
                ],
            },
            {
                "type": "message",
                "role": "assistant",
                "content": [
                    {"type": "output_text", "text": " third", "annotations": []},
                ],
            },
        ],
        **metadata,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "limits",
    [
        {"max_output_tokens": 64},
        {"max_tokens": 64},
        {"max_completion_tokens": 64},
        {"max_tokens": 64, "max_output_tokens": 64},
        {"max_completion_tokens": 64, "max_output_tokens": 64},
    ],
)
async def test_native_stateless_request_and_metadata(adapter, respx_mock, limits):
    route = respx_mock.post(URL).mock(
        return_value=httpx.Response(
            200,
            json=body(
                usage={"input_tokens": 7, "output_tokens": 5, "total_tokens": 12, "cost": 99},
            ),
        )
    )
    result = await adapter().complete(
        candidate(
            {
                "temperature": 0.2,
                "reasoning": {"effort": "low"},
                **limits,
            }
        ),
        case(),
        0,
    )
    request = route.calls[0].request
    assert request.headers["Authorization"] == "Bearer secret-token"
    assert json.loads(request.content) == {
        "model": "gpt-native-model",
        "store": False,
        "input": [{"role": "system", "content": "Be brief."}, {"role": "user", "content": "hello"}],
        "temperature": 0.2,
        "reasoning": {"effort": "low"},
        "max_output_tokens": 64,
    }
    assert result.raw_output == "first second third"
    assert (result.input_tokens, result.output_tokens, result.total_tokens) == (7, 5, 12)
    assert (result.provider, result.model) == ("openai", "gpt-actual-model")
    assert result.cost_usd is result.provider_backend is None
    assert result.latency_ms >= 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "parameters",
    [
        {"max_tokens": 64, "max_completion_tokens": 64},
        {"max_tokens": 64, "max_output_tokens": 65},
        {"max_completion_tokens": 64, "max_output_tokens": 65},
        {"model": "secret-token"},
        {"input": "secret-token"},
        {"store": False},
    ],
)
async def test_conflicts_fail_safely_before_http(adapter, respx_mock, parameters):
    with pytest.raises(ProviderError) as caught:
        await adapter().complete(candidate(parameters), case(), 0)
    assert (caught.value.kind, caught.value.retryable) == ("configuration", False)
    assert "secret-token" not in str(caught.value)
    assert not respx_mock.calls


@pytest.mark.asyncio
async def test_other_parameters_are_forwarded_to_provider(adapter, respx_mock):
    route = respx_mock.post(URL).mock(
        return_value=httpx.Response(
            400,
            json={"error": {"message": "secret-token response-body"}},
        )
    )
    parameters = {"response_format": {"type": "json_object"}, "unknown_field": [1, 2]}
    with pytest.raises(ProviderError) as caught:
        await adapter().complete(candidate(parameters), case(), 0)
    payload = json.loads(route.calls[0].request.content)
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["unknown_field"] == [1, 2]
    assert (caught.value.kind, caught.value.retryable) == ("http", False)
    assert "secret-token" not in str(caught.value)
    assert "response-body" not in str(caught.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "metadata",
    [
        {"model": None},
        {"usage": None, "model": []},
        {"usage": [], "model": ""},
        {"usage": {"input_tokens": True, "output_tokens": -1, "total_tokens": "12"}},
    ],
)
async def test_missing_or_invalid_optional_metadata_is_safe(adapter, respx_mock, metadata):
    respx_mock.post(URL).mock(return_value=httpx.Response(200, json=body(**metadata)))
    result = await adapter().complete(candidate(), case(), 0)
    assert result.raw_output == "first second third"
    assert result.input_tokens is result.output_tokens is result.total_tokens is None
    assert result.model == ("gpt-actual-model" if "model" not in metadata else "gpt-native-model")
    assert result.cost_usd is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        "invalid-json",
        "[]",
        "{}",
        json.dumps(body(status="incomplete")),
        json.dumps(body(output=[])),
        json.dumps(body(output=None)),
        json.dumps(body(output={"type": "message"})),
        json.dumps(body(output=[{"type": "reasoning", "summary": []}])),
        json.dumps(body(output=[{"type": "message", "content": None}])),
        json.dumps(
            body(
                output=[
                    {
                        "type": "message",
                        "content": [
                            {"type": "output_text", "text": 123},
                        ],
                    }
                ]
            )
        ),
        json.dumps(
            body(
                output=[
                    {
                        "type": "message",
                        "content": [
                            {"type": "output_text", "text": ""},
                        ],
                    }
                ]
            )
        ),
    ],
)
async def test_unusable_or_incomplete_response_is_normalized(adapter, respx_mock, response):
    respx_mock.post(URL).mock(return_value=httpx.Response(200, text=response))
    with pytest.raises(ProviderError) as caught:
        await adapter().complete(candidate(), case(), 0)
    assert (caught.value.kind, caught.value.retryable) == ("response", False)
    assert "secret-token" not in str(caught.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,code,kind,retryable",
    [
        (401, "invalid_api_key", "authentication", False),
        (403, None, "permission", False),
        (408, None, "timeout", True),
        (429, "rate_limit_exceeded", "rate_limit", True),
        (429, "insufficient_quota", "rate_limit", False),
        (429, "billing_hard_limit_reached", "rate_limit", False),
        (429, None, "rate_limit", True),
        (500, None, "server", True),
        (503, None, "server", True),
    ],
)
async def test_http_errors_are_secret_safe(adapter, respx_mock, status, code, kind, retryable):
    respx_mock.post(URL).mock(
        return_value=httpx.Response(
            status,
            json={
                "error": {"code": code, "message": "secret-token response-body"},
            },
        )
    )
    with pytest.raises(ProviderError) as caught:
        await adapter().complete(candidate(), case(), 0)
    assert (caught.value.kind, caught.value.retryable) == (kind, retryable)
    assert "secret-token" not in str(caught.value)
    assert "response-body" not in str(caught.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exception,kind,retryable",
    [
        (httpx.ReadTimeout, "timeout", True),
        (httpx.ConnectError, "network", True),
        (httpx.RemoteProtocolError, "http", False),
    ],
)
async def test_transport_errors_are_secret_safe(adapter, respx_mock, exception, kind, retryable):
    respx_mock.post(URL).mock(side_effect=exception("secret-token response-body"))
    with pytest.raises(ProviderError) as caught:
        await adapter().complete(candidate(), case(), 0)
    assert (caught.value.kind, caught.value.retryable) == (kind, retryable)
    assert "secret-token" not in str(caught.value)
    assert "response-body" not in str(caught.value)


def test_exact_openai_environment_credential(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "required-token")
    assert EnvironmentCredentialResolver().resolve(None, "openai") == "required-token"


def test_missing_openai_credential_is_safe(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPEN_AI_API_KEY", "wrong-spelling-token")
    with pytest.raises(MissingCredentialError) as caught:
        EnvironmentCredentialResolver().resolve(None, "openai")
    assert "OPENAI_API_KEY" in str(caught.value)
    assert "wrong-spelling-token" not in str(caught.value)
