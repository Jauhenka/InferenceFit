"""Native, non-streaming Anthropic Messages transport."""

from __future__ import annotations

import time
from typing import Any

import httpx

from inferencefit.contracts import CandidateSpec, TestCase

from .base import ProviderError, ProviderResponse
from .http_errors import provider_error_from_response

_URL = "https://api.anthropic.com/v1/messages"
_VERSION = "2023-06-01"
_DEFAULT_MAX_TOKENS = 1024
_RESERVED_PARAMETERS = frozenset({"model", "messages", "system", "stream"})


def _token_count(usage: dict[str, Any], name: str) -> int | None:
    value = usage.get(name)
    return value if type(value) is int and value >= 0 else None


class AnthropicProvider:
    def __init__(self, credential: str | None = None):
        self.credential = credential

    async def complete(
        self, candidate: CandidateSpec, case: TestCase, repetition: int
    ) -> ProviderResponse:
        parameters = dict(candidate.parameters)
        if _RESERVED_PARAMETERS.intersection(parameters):
            raise ProviderError("reserved Anthropic Messages parameter", kind="configuration")

        max_tokens = parameters.pop("max_tokens", None)
        alias = parameters.pop("max_output_tokens", None)
        if max_tokens is not None and alias is not None and max_tokens != alias:
            raise ProviderError("conflicting output token limits", kind="configuration")
        limit = max_tokens if max_tokens is not None else alias
        if limit is None:
            limit = _DEFAULT_MAX_TOKENS
        if type(limit) is not int or limit <= 0:
            raise ProviderError("invalid output token limit", kind="configuration")

        system: list[str] = []
        messages: list[dict[str, str]] = []
        for message in case.request.messages:
            if message.name is not None:
                raise ProviderError("named messages are unsupported", kind="configuration")
            if message.role == "system":
                if messages:
                    raise ProviderError(
                        "system message must precede conversation", kind="configuration"
                    )
                system.append(message.content)
            else:
                messages.append({"role": message.role, "content": message.content})
        if not messages:
            raise ProviderError(
                "conversation requires a user or assistant message", kind="configuration"
            )

        payload: dict[str, Any] = {
            "model": candidate.model,
            "max_tokens": limit,
            "messages": messages,
            **parameters,
        }
        if system:
            payload["system"] = "\n\n".join(system)
        headers = {"anthropic-version": _VERSION}
        if self.credential:
            headers["x-api-key"] = self.credential

        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                response = await client.post(_URL, json=payload, headers=headers)
            if response.is_error or response.is_redirect:
                raise provider_error_from_response(response, provider="anthropic")
            try:
                data = response.json()
                blocks = data["content"]
                if not isinstance(blocks, list):
                    raise TypeError
                text_blocks = []
                for block in blocks:
                    if not isinstance(block, dict):
                        raise TypeError
                    if block.get("type") == "text":
                        value = block["text"]
                        if not isinstance(value, str):
                            raise TypeError
                        text_blocks.append(value)
                content = "".join(text_blocks)
                if not content:
                    raise ValueError
            except (ValueError, KeyError, IndexError, TypeError):
                raise ProviderError("malformed provider response", kind="response") from None

            usage = data.get("usage")
            if not isinstance(usage, dict):
                usage = {}
            input_tokens = _token_count(usage, "input_tokens")
            if input_tokens is not None:
                for name in ("cache_creation_input_tokens", "cache_read_input_tokens"):
                    if name in usage:
                        extra = _token_count(usage, name)
                        input_tokens = input_tokens + extra if extra is not None else None
                        if input_tokens is None:
                            break
            output_tokens = _token_count(usage, "output_tokens")
            total_tokens = (
                input_tokens + output_tokens
                if input_tokens is not None and output_tokens is not None
                else None
            )
            model = data.get("model")
            if not isinstance(model, str) or not model:
                model = candidate.model
            return ProviderResponse(
                raw_output=content,
                latency_ms=(time.perf_counter() - started) * 1000,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                provider="anthropic",
                model=model,
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
