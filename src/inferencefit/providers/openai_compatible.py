from __future__ import annotations

import time

import httpx

from inferencefit.contracts import CandidateSpec, TestCase

from .base import ProviderError, ProviderResponse
from .http_errors import provider_error_from_response
from .metadata import (
    nonempty_string,
    nonnegative_token_count,
    normalize_finish_reason,
    provider_request_id,
    safe_native_response,
)

PRESET_URLS = {
    "chutes": "https://llm.chutes.ai/v1",
    "deepseek": "https://api.deepseek.com",
    "openrouter": "https://openrouter.ai/api/v1",
    "fireworks": "https://api.fireworks.ai/inference/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "morpheus": "https://api.mor.org/api/v1",
    "nosana": "https://inference.nosana.com/v1",
    "ollama": "http://127.0.0.1:11434/v1",
    "vllm": "http://127.0.0.1:8000/v1",
}


class OpenAICompatibleProvider:
    def __init__(self, credential: str | None = None):
        self.credential = credential

    def _base_url(self, candidate: CandidateSpec) -> str | None:
        return candidate.base_url or PRESET_URLS.get(candidate.provider)

    def _request_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.credential}"} if self.credential else {}

    def _response_metadata(self, data: dict) -> dict:
        return {}

    async def complete(
        self, candidate: CandidateSpec, case: TestCase, repetition: int
    ) -> ProviderResponse:
        if {"model", "messages", "stream"}.intersection(candidate.parameters):
            raise ProviderError("reserved chat-completions parameter", kind="configuration")
        base_url = self._base_url(candidate)
        if not base_url:
            raise ProviderError("OpenAI-compatible candidate requires base_url")
        headers = self._request_headers()
        payload = {
            "model": candidate.model,
            "messages": [x.model_dump(exclude_none=True) for x in case.request.messages],
            **candidate.parameters,
        }
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                response = await client.post(
                    f"{base_url.rstrip('/')}/chat/completions", json=payload, headers=headers
                )
            if response.is_error or response.is_redirect:
                raise provider_error_from_response(response, provider=candidate.provider)
            try:
                data = response.json()
                content = data["choices"][0]["message"]["content"]
            except (ValueError, KeyError, IndexError, TypeError):
                raise ProviderError("malformed provider response", kind="response") from None
            if not isinstance(content, str):
                raise ProviderError("malformed provider response", kind="response")
            usage = data.get("usage")
            if not isinstance(usage, dict):
                usage = {}
            model = data.get("model")
            if not isinstance(model, str) or not model:
                model = candidate.model

            def token_count(name: str) -> int | None:
                value = usage.get(name)
                return value if type(value) is int and value >= 0 else None

            native = safe_native_response(data, self.credential)
            native_usage = native.get("usage")
            native_choice = native["choices"][0]
            native_reason = nonempty_string(native_choice.get("finish_reason"))
            message = native_choice.get("message")
            reasoning_content = (
                nonempty_string(message.get("reasoning_content"))
                if isinstance(message, dict)
                else None
            )
            details = usage.get("completion_tokens_details")
            if not isinstance(details, dict):
                details = usage.get("output_tokens_details")
            reasoning_tokens = (
                nonnegative_token_count(details.get("reasoning_tokens"))
                if isinstance(details, dict)
                else None
            )

            return ProviderResponse(
                raw_output=content,
                latency_ms=(time.perf_counter() - started) * 1000,
                input_tokens=token_count("prompt_tokens"),
                output_tokens=token_count("completion_tokens"),
                total_tokens=token_count("total_tokens"),
                provider=candidate.provider,
                model=model,
                raw_response=native,
                finish_reason=normalize_finish_reason(native_reason),
                provider_finish_reason=native_reason,
                provider_request_id=provider_request_id(response, self.credential),
                reasoning_tokens=reasoning_tokens,
                reasoning_content=reasoning_content,
                usage_details=native_usage if isinstance(native_usage, dict) else None,
                **self._response_metadata(data),
            )
        except ProviderError:
            raise
        except httpx.TimeoutException:
            raise ProviderError(
                "provider request timeout", retryable=True, kind="timeout"
            ) from None
        except httpx.NetworkError:
            raise ProviderError(
                "provider network failure", retryable=True, kind="network"
            ) from None
        except httpx.HTTPError:
            raise ProviderError("provider HTTP failure", kind="http") from None
