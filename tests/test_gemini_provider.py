"""Offline Gemini-compatible provider and credential contracts."""

import json

import httpx
import pytest

from inferencefit.contracts import CandidateSpec
from inferencefit.contracts import TestCase as Case
from inferencefit.credentials import EnvironmentCredentialResolver
from inferencefit.errors import MissingCredentialError
from inferencefit.providers import ProviderError
from inferencefit.providers.openai_compatible import OpenAICompatibleProvider

URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"


def candidate():
    return CandidateSpec(
        id="gemini",
        provider="gemini",
        model="gemini-2.5-flash",
        parameters={"temperature": 0.2, "top_p": 0.9, "max_tokens": 64},
    )


def case():
    return Case.model_validate(
        {
            "id": "c",
            "request": {
                "messages": [
                    {"role": "system", "content": "Answer briefly."},
                    {"role": "user", "content": "hello"},
                ]
            },
        }
    )


def body(**metadata):
    return {"choices": [{"message": {"content": "hello back"}}], **metadata}


@pytest.mark.asyncio
async def test_gemini_uses_native_chat_request_and_normalizes_reported_usage(respx_mock):
    route = respx_mock.post(URL).mock(
        return_value=httpx.Response(
            200,
            json=body(
                model="gemini-2.5-flash-002",
                usage={"prompt_tokens": 7, "completion_tokens": 4, "total_tokens": 11},
            ),
        )
    )

    result = await OpenAICompatibleProvider("gemini-secret").complete(candidate(), case(), 0)

    request = route.calls[0].request
    assert request.headers["Authorization"] == "Bearer gemini-secret"
    assert json.loads(request.content) == {
        "model": "gemini-2.5-flash",
        "messages": [
            {"role": "system", "content": "Answer briefly."},
            {"role": "user", "content": "hello"},
        ],
        "temperature": 0.2,
        "top_p": 0.9,
        "max_tokens": 64,
    }
    assert result.raw_output == "hello back"
    assert (result.input_tokens, result.output_tokens, result.total_tokens) == (7, 4, 11)
    assert (result.provider, result.model) == ("gemini", "gemini-2.5-flash-002")
    assert result.latency_ms >= 0
    assert result.cost_usd is None
    assert route.called


@pytest.mark.asyncio
@pytest.mark.parametrize("usage", [None, [], "unavailable"])
async def test_missing_or_invalid_optional_usage_keeps_text_and_unknown_cost(respx_mock, usage):
    respx_mock.post(URL).mock(return_value=httpx.Response(200, json=body(usage=usage)))

    result = await OpenAICompatibleProvider().complete(candidate(), case(), 0)

    assert result.raw_output == "hello back"
    assert (result.input_tokens, result.output_tokens, result.total_tokens) == (None, None, None)
    assert result.model == "gemini-2.5-flash"
    assert result.cost_usd is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response", ["not-json", "{}", '{"choices": []}', '{"choices": [{"message": {}}]}']
)
async def test_malformed_responses_are_nonretryable_and_redacted(respx_mock, response):
    respx_mock.post(URL).mock(return_value=httpx.Response(200, text=response))

    with pytest.raises(ProviderError) as caught:
        await OpenAICompatibleProvider("gemini-secret").complete(candidate(), case(), 0)

    assert (caught.value.kind, caught.value.retryable) == ("response", False)
    assert "gemini-secret" not in str(caught.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,kind,retryable",
    [(401, "authentication", False), (429, "rate_limit", True), (503, "server", True)],
)
async def test_http_failures_use_shared_classification_and_redact_remote_content(
    respx_mock, status, kind, retryable
):
    respx_mock.post(URL).mock(
        return_value=httpx.Response(status, text="gemini-secret upstream-secret")
    )

    with pytest.raises(ProviderError) as caught:
        await OpenAICompatibleProvider("gemini-secret").complete(candidate(), case(), 0)

    assert (caught.value.kind, caught.value.retryable) == (kind, retryable)
    assert "gemini-secret" not in str(caught.value)
    assert "upstream-secret" not in str(caught.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exception,kind", [(httpx.ReadTimeout, "timeout"), (httpx.ConnectError, "network")]
)
async def test_transport_failures_are_retryable_and_redacted(respx_mock, exception, kind):
    respx_mock.post(URL).mock(side_effect=exception("gemini-secret"))

    with pytest.raises(ProviderError) as caught:
        await OpenAICompatibleProvider("gemini-secret").complete(candidate(), case(), 0)

    assert (caught.value.kind, caught.value.retryable) == (kind, True)
    assert "gemini-secret" not in str(caught.value)


def test_exact_gemini_credential_fallback(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_KEY", "wrong-name-secret")
    with pytest.raises(MissingCredentialError) as caught:
        EnvironmentCredentialResolver().resolve(None, "gemini")
    assert "wrong-name-secret" not in str(caught.value)

    monkeypatch.setenv("GEMINI_API_KEY", "gemini-secret")
    assert EnvironmentCredentialResolver().resolve(None, "gemini") == "gemini-secret"
