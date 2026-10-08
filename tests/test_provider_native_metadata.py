"""Provider-native metadata from existing HTTP response objects, offline only."""

import json

import httpx
import pytest

from inferencefit.contracts import CandidateSpec
from inferencefit.contracts import TestCase as Case
from inferencefit.providers.openai_compatible import OpenAICompatibleProvider
from inferencefit.providers.openai_responses import OpenAIResponsesProvider


def case():
    return Case.model_validate(
        {"id": "c", "request": {"messages": [{"role": "user", "content": "hello"}]}}
    )


@pytest.mark.asyncio
async def test_openai_responses_exposes_only_returned_reasoning_and_usage(respx_mock):
    native = {
        "status": "completed",
        "model": "served-model",
        "output": [
            {
                "type": "reasoning",
                "summary": [{"type": "summary_text", "text": "Visible summary"}],
                "encrypted_content": "opaque-ciphertext",
            },
            {"type": "message", "content": [{"type": "output_text", "text": "answer"}]},
        ],
        "usage": {
            "input_tokens": 4,
            "input_tokens_details": {"cached_tokens": 2},
            "output_tokens": 12,
            "output_tokens_details": {"reasoning_tokens": 8},
            "total_tokens": 16,
        },
    }
    respx_mock.post("https://api.openai.com/v1/responses").mock(
        return_value=httpx.Response(200, json=native, headers={"x-request-id": "req-openai"})
    )
    result = await OpenAIResponsesProvider("test-secret").complete(
        CandidateSpec(id="x", provider="openai", model="opaque"), case(), 0
    )
    assert result.raw_response == native
    assert result.raw_output == "answer"
    assert result.finish_reason == "stop"
    assert result.provider_finish_reason == "completed"
    assert result.provider_request_id == "req-openai"
    assert result.reasoning_tokens == 8
    assert result.reasoning_content == "Visible summary"
    assert result.usage_details == native["usage"]
    assert result.output_tokens == 12


@pytest.mark.asyncio
async def test_openai_missing_reasoning_stays_none(respx_mock):
    native = {
        "status": "completed",
        "output": [{"type": "message", "content": [{"type": "output_text", "text": "answer"}]}],
        "usage": {"input_tokens": 2, "output_tokens": 3, "total_tokens": 5},
    }
    respx_mock.post("https://api.openai.com/v1/responses").mock(
        return_value=httpx.Response(200, json=native)
    )
    result = await OpenAIResponsesProvider().complete(
        CandidateSpec(id="x", provider="openai", model="opaque"), case(), 0
    )
    assert result.reasoning_tokens is None
    assert result.reasoning_content is None
    assert result.provider_request_id is None
    assert result.output_tokens == 3


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider,url",
    [
        ("gemini", "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"),
        ("deepseek", "https://api.deepseek.com/chat/completions"),
        ("fireworks", "https://api.fireworks.ai/inference/v1/chat/completions"),
    ],
)
async def test_chat_provider_native_metadata(provider, url, respx_mock):
    native = {
        "model": "served-model",
        "choices": [
            {
                "finish_reason": "length",
                "message": {"content": "answer", "reasoning_content": "returned reasoning"},
            }
        ],
        "usage": {
            "prompt_tokens": 3,
            "completion_tokens": 11,
            "total_tokens": 14,
            "prompt_tokens_details": {"cached_tokens": 2},
            "completion_tokens_details": {"reasoning_tokens": 7},
        },
    }
    respx_mock.post(url).mock(
        return_value=httpx.Response(200, json=native, headers={"x-request-id": "req-chat"})
    )
    result = await OpenAICompatibleProvider("test-secret").complete(
        CandidateSpec(id="x", provider=provider, model="opaque"), case(), 0
    )
    assert result.raw_response == native
    assert result.finish_reason == "length"
    assert result.provider_finish_reason == "length"
    assert result.provider_request_id == "req-chat"
    assert result.reasoning_tokens == 7
    assert result.reasoning_content == "returned reasoning"
    assert result.usage_details == native["usage"]
    assert result.output_tokens == 11
    assert "test-secret" not in json.dumps(result.raw_response)


@pytest.mark.asyncio
async def test_unknown_chat_finish_reason_is_preserved_without_guessing(respx_mock):
    native = {
        "choices": [{"finish_reason": "future_reason", "message": {"content": "answer"}}],
    }
    respx_mock.post("https://api.deepseek.com/chat/completions").mock(
        return_value=httpx.Response(200, json=native)
    )
    result = await OpenAICompatibleProvider().complete(
        CandidateSpec(id="x", provider="deepseek", model="opaque"), case(), 0
    )
    assert result.provider_finish_reason == "future_reason"
    assert result.finish_reason is None
    assert result.reasoning_tokens is None
    assert result.reasoning_content is None
    assert result.usage_details is None
