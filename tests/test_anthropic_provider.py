"""Native Anthropic Messages adapter contracts, exercised without network access."""

import json

import httpx
import pytest

from inferencefit.contracts import CandidateSpec
from inferencefit.contracts import TestCase as Case
from inferencefit.credentials import EnvironmentCredentialResolver
from inferencefit.errors import MissingCredentialError
from inferencefit.providers import OpenAICompatibleProvider, ProviderError, create_provider

URL = "https://api.anthropic.com/v1/messages"


def candidate(provider="anthropic", **kwargs):
    return CandidateSpec(id="claude", provider=provider, model="opaque-model-id", **kwargs)


def case(messages=None):
    return Case.model_validate(
        {
            "id": "case",
            "request": {
                "messages": messages or [{"role": "user", "content": "Hello"}],
            },
        }
    )


def response(**overrides):
    return {
        "model": "returned-model-id",
        "content": [{"type": "text", "text": "Hello back"}],
        "usage": {"input_tokens": 3, "output_tokens": 2},
        **overrides,
    }


@pytest.mark.parametrize("provider", ["anthropic", "claude"])
def test_native_names_share_adapter_and_key_fallback(provider, tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-secret")
    from inferencefit.providers import AnthropicProvider

    adapter = create_provider(
        candidate(provider), spec_dir=tmp_path, resolver=EnvironmentCredentialResolver()
    )
    assert type(adapter) is AnthropicProvider
    assert adapter.credential == "test-anthropic-secret"


@pytest.mark.parametrize("provider", ["anthropic", "claude"])
def test_credential_reference_precedes_provider_fallback(provider, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fallback-secret")
    monkeypatch.setenv("INFERENCEFIT_CREDENTIAL_MY_CLAUDE", "reference-secret")
    assert EnvironmentCredentialResolver().resolve("my-claude", provider) == "reference-secret"


@pytest.mark.parametrize("provider", ["anthropic", "claude"])
def test_missing_key_error_does_not_include_secret(provider, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(MissingCredentialError) as caught:
        EnvironmentCredentialResolver().resolve(None, provider)
    assert "ANTHROPIC_API_KEY" in str(caught.value)


@pytest.mark.parametrize("provider", ["anthropic", "claude"])
def test_explicit_base_url_keeps_generic_override(provider, tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-secret")
    adapter = create_provider(
        candidate(provider, base_url="https://proxy.example/v1"),
        spec_dir=tmp_path,
        resolver=EnvironmentCredentialResolver(),
    )
    assert type(adapter) is OpenAICompatibleProvider


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["anthropic", "claude"])
async def test_messages_request_and_text_usage(provider, respx_mock):
    route = respx_mock.post(URL).mock(
        return_value=httpx.Response(
            200,
            json=response(
                content=[
                    {"type": "thinking", "thinking": "not output"},
                    {"type": "text", "text": "Hello"},
                    {"type": "text", "text": " back"},
                ],
                usage={
                    "input_tokens": 3,
                    "cache_creation_input_tokens": 5,
                    "cache_read_input_tokens": 7,
                    "output_tokens": 2,
                },
            ),
        )
    )
    from inferencefit.providers import AnthropicProvider

    result = await AnthropicProvider("test-secret").complete(
        candidate(provider, parameters={"temperature": 0.4, "max_tokens": 64}),
        case(
            [
                {"role": "system", "content": "Be concise."},
                {"role": "system", "content": "Be helpful."},
                {"role": "user", "content": "Hi"},
                {"role": "assistant", "content": "Hello"},
                {"role": "user", "content": "Again"},
            ]
        ),
        0,
    )
    request = route.calls[0].request
    assert request.headers["x-api-key"] == "test-secret"
    assert request.headers["anthropic-version"] == "2023-06-01"
    assert "Authorization" not in request.headers
    assert json.loads(request.content) == {
        "model": "opaque-model-id",
        "max_tokens": 64,
        "temperature": 0.4,
        "system": "Be concise.\n\nBe helpful.",
        "messages": [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello"},
            {"role": "user", "content": "Again"},
        ],
    }
    assert (result.raw_output, result.provider, result.model) == (
        "Hello back",
        "anthropic",
        "returned-model-id",
    )
    assert (result.input_tokens, result.output_tokens, result.total_tokens) == (15, 2, 17)
    assert result.cost_usd is None
    assert result.latency_ms >= 0


@pytest.mark.asyncio
async def test_default_max_tokens_and_no_implicit_temperature(respx_mock):
    route = respx_mock.post(URL).mock(return_value=httpx.Response(200, json=response()))
    from inferencefit.providers import AnthropicProvider

    await AnthropicProvider().complete(candidate(), case(), 0)
    payload = json.loads(route.calls[0].request.content)
    assert payload["max_tokens"] == 1024
    assert "temperature" not in payload
    assert "stream" not in payload
    assert "system" not in payload


@pytest.mark.asyncio
async def test_max_output_tokens_alias_maps_to_native_limit(respx_mock):
    route = respx_mock.post(URL).mock(return_value=httpx.Response(200, json=response()))
    from inferencefit.providers import AnthropicProvider

    await AnthropicProvider().complete(candidate(parameters={"max_output_tokens": 25}), case(), 0)
    payload = json.loads(route.calls[0].request.content)
    assert payload["max_tokens"] == 25
    assert "max_output_tokens" not in payload


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "parameters",
    [
        {"stream": True},
        {"model": "override"},
        {"messages": []},
        {"system": "override"},
        {"max_tokens": 10, "max_output_tokens": 20},
        {"max_tokens": 0},
        {"max_tokens": True},
    ],
)
async def test_unsafe_or_ambiguous_parameters_fail_before_http(parameters, respx_mock):
    from inferencefit.providers import AnthropicProvider

    with pytest.raises(ProviderError) as caught:
        await AnthropicProvider().complete(candidate(parameters=parameters), case(), 0)
    assert caught.value.kind == "configuration"
    assert not respx_mock.calls


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "messages",
    [
        [{"role": "system", "content": "only system"}],
        [{"role": "user", "content": "Hi"}, {"role": "system", "content": "late"}],
        [{"role": "user", "content": "Hi", "name": "someone"}],
    ],
)
async def test_unrepresentable_messages_fail_before_http(messages, respx_mock):
    from inferencefit.providers import AnthropicProvider

    with pytest.raises(ProviderError) as caught:
        await AnthropicProvider().complete(candidate(), case(messages), 0)
    assert caught.value.kind == "configuration"
    assert not respx_mock.calls


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        "not-json",
        "{}",
        '{"content": []}',
        '{"content": [{"type": "thinking", "thinking": "secret"}]}',
        '{"content": [{"type": "text", "text": 3}]}',
    ],
)
async def test_malformed_or_nontext_response_is_safe_error(respx_mock, body):
    respx_mock.post(URL).mock(return_value=httpx.Response(200, text=body))
    from inferencefit.providers import AnthropicProvider

    with pytest.raises(ProviderError) as caught:
        await AnthropicProvider("test-secret").complete(candidate(), case(), 0)
    assert (caught.value.kind, caught.value.retryable) == ("response", False)
    assert "test-secret" not in str(caught.value)
    assert "secret" not in str(caught.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,kind,retryable",
    [
        (401, "authentication", False),
        (403, "permission", False),
        (429, "rate_limit", True),
        (529, "server", True),
    ],
)
async def test_http_error_uses_shared_safe_classification(respx_mock, status, kind, retryable):
    respx_mock.post(URL).mock(return_value=httpx.Response(status, text="test-secret remote-secret"))
    from inferencefit.providers import AnthropicProvider

    with pytest.raises(ProviderError) as caught:
        await AnthropicProvider("test-secret").complete(candidate(), case(), 0)
    assert (caught.value.kind, caught.value.retryable) == (kind, retryable)
    assert "test-secret" not in str(caught.value)
    assert "remote-secret" not in str(caught.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error,kind",
    [(httpx.ReadTimeout, "timeout"), (httpx.ConnectError, "network")],
)
async def test_transport_failures_are_retryable_and_safe(respx_mock, error, kind):
    respx_mock.post(URL).mock(side_effect=error("test-secret"))
    from inferencefit.providers import AnthropicProvider

    with pytest.raises(ProviderError) as caught:
        await AnthropicProvider("test-secret").complete(candidate(), case(), 0)
    assert (caught.value.kind, caught.value.retryable) == (kind, True)
    assert "test-secret" not in str(caught.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["anthropic", "claude"])
@pytest.mark.parametrize("workspace", [None, "", "wrkspc_test123"])
async def test_workspace_header_for_both_names(
    provider, workspace, tmp_path, monkeypatch, respx_mock
):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-secret")
    if workspace is None:
        monkeypatch.delenv("ANTHROPIC_WORKSPACE_ID", raising=False)
    else:
        monkeypatch.setenv("ANTHROPIC_WORKSPACE_ID", workspace)
    route = respx_mock.post(URL).mock(return_value=httpx.Response(200, json=response()))
    adapter = create_provider(
        candidate(provider), spec_dir=tmp_path, resolver=EnvironmentCredentialResolver()
    )
    await adapter.complete(candidate(provider), case(), 0)
    headers = route.calls[0].request.headers
    assert headers["x-api-key"] == "test-secret"
    if not workspace:
        assert "anthropic-workspace-id" not in headers
    else:
        assert headers["anthropic-workspace-id"] == workspace


@pytest.mark.asyncio
async def test_invalid_workspace_header_fails_safely_before_http(monkeypatch, respx_mock):
    from inferencefit.providers import AnthropicProvider

    monkeypatch.setenv("ANTHROPIC_WORKSPACE_ID", "wrkspc_test\r\nx-api-key: stolen")
    with pytest.raises(ProviderError) as caught:
        await AnthropicProvider("test-secret").complete(candidate(), case(), 0)
    assert caught.value.kind == "configuration"
    assert "stolen" not in str(caught.value)
    assert not respx_mock.calls


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "native,normalized",
    [
        ("end_turn", "stop"),
        ("stop_sequence", "stop"),
        ("max_tokens", "length"),
        ("tool_use", "tool_calls"),
        ("pause_turn", "pause"),
        ("refusal", "refusal"),
        ("model_context_window_exceeded", "length"),
        ("future_stop_reason", None),
    ],
)
async def test_native_stop_reason_preserved_and_normalized(respx_mock, native, normalized):
    from inferencefit.providers import AnthropicProvider

    respx_mock.post(URL).mock(return_value=httpx.Response(200, json=response(stop_reason=native)))
    result = await AnthropicProvider().complete(candidate(), case(), 0)
    assert result.provider_finish_reason == native
    assert result.finish_reason == normalized
    assert result.raw_response["stop_reason"] == native


@pytest.mark.asyncio
async def test_native_response_keeps_thinking_text_request_id_and_cache_usage(respx_mock):
    from inferencefit.providers import AnthropicProvider

    native = response(
        stop_reason="end_turn",
        content=[
            {"type": "thinking", "thinking": "first", "signature": "opaque"},
            {"type": "text", "text": "Hello"},
            {"type": "thinking", "thinking": "second", "signature": "opaque2"},
            {"type": "text", "text": " back"},
        ],
        usage={
            "input_tokens": 3,
            "cache_creation_input_tokens": 5,
            "cache_read_input_tokens": 7,
            "output_tokens": 10,
        },
    )
    respx_mock.post(URL).mock(
        return_value=httpx.Response(200, json=native, headers={"request-id": "req-native-123"})
    )
    result = await AnthropicProvider().complete(candidate(), case(), 0)
    assert result.raw_output == "Hello back"
    assert result.raw_response == native
    assert result.reasoning_content == "first\n\nsecond"
    assert result.reasoning_tokens is None  # Anthropic usage did not separately report these.
    assert result.provider_request_id == "req-native-123"
    assert result.usage_details == native["usage"]
    assert (result.input_tokens, result.output_tokens, result.total_tokens) == (15, 10, 25)


@pytest.mark.asyncio
async def test_missing_native_metadata_stays_none(respx_mock):
    from inferencefit.providers import AnthropicProvider

    respx_mock.post(URL).mock(return_value=httpx.Response(200, json=response()))
    result = await AnthropicProvider().complete(candidate(), case(), 0)
    assert result.finish_reason is None
    assert result.provider_finish_reason is None
    assert result.provider_request_id is None
    assert result.reasoning_tokens is None
    assert result.reasoning_content is None


@pytest.mark.asyncio
async def test_new_native_artifact_fields_redact_echoed_api_key(respx_mock):
    from inferencefit.providers import AnthropicProvider

    native = response(metadata={"authorization": "Bearer test-secret", "note": "test-secret"})
    respx_mock.post(URL).mock(return_value=httpx.Response(200, json=native))
    result = await AnthropicProvider("test-secret").complete(candidate(), case(), 0)
    assert "test-secret" not in json.dumps(result.raw_response)
    assert result.raw_response["content"] == native["content"]


@pytest.mark.asyncio
async def test_explicit_reasoning_count_does_not_change_total_output(respx_mock):
    from inferencefit.providers import AnthropicProvider

    native = response(usage={"input_tokens": 2, "output_tokens": 10, "reasoning_tokens": 7})
    respx_mock.post(URL).mock(return_value=httpx.Response(200, json=native))
    result = await AnthropicProvider().complete(candidate(), case(), 0)
    assert result.reasoning_tokens == 7
    assert result.output_tokens == 10
    assert result.total_tokens == 12
