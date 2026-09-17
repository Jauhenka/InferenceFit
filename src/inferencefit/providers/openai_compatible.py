from __future__ import annotations

import time

import httpx

from inferencefit.contracts import CandidateSpec, TestCase

from .base import ProviderError, ProviderResponse

PRESET_URLS = {
    "openrouter": "https://openrouter.ai/api/v1",
    "fireworks": "https://api.fireworks.ai/inference/v1",
    "ollama": "http://127.0.0.1:11434/v1",
    "vllm": "http://127.0.0.1:8000/v1",
}


class OpenAICompatibleProvider:
    def __init__(self, credential: str | None = None):
        self.credential = credential

    async def complete(
        self, candidate: CandidateSpec, case: TestCase, repetition: int
    ) -> ProviderResponse:
        base_url = candidate.base_url or PRESET_URLS.get(candidate.provider)
        if not base_url:
            raise ProviderError("OpenAI-compatible candidate requires base_url")
        headers = {"Authorization": f"Bearer {self.credential}"} if self.credential else {}
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
            if response.status_code == 429 or 500 <= response.status_code < 600:
                raise ProviderError(
                    f"provider HTTP {response.status_code}", retryable=True, kind="http"
                )
            response.raise_for_status()
            try:
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})
            except (ValueError, KeyError, IndexError, TypeError) as exc:
                raise ProviderError("malformed provider response", kind="response") from exc
            return ProviderResponse(
                raw_output=content,
                latency_ms=(time.perf_counter() - started) * 1000,
                input_tokens=usage.get("prompt_tokens"),
                output_tokens=usage.get("completion_tokens"),
                provider=candidate.provider,
                model=data.get("model", candidate.model),
            )
        except ProviderError:
            raise
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise ProviderError(type(exc).__name__, retryable=True, kind="network") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(type(exc).__name__, kind="http") from exc
