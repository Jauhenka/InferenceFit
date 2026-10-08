"""Stateless requests to OpenAI's native Responses API."""

from __future__ import annotations

import time

import httpx

from inferencefit.contracts import CandidateSpec, TestCase

from .base import ProviderError, ProviderResponse
from .http_errors import provider_error_from_response
from .metadata import (
    nonempty_string,
    nonnegative_token_count,
    provider_request_id,
    safe_native_response,
)


class OpenAIResponsesProvider:
    def __init__(self, credential: str | None = None):
        self.credential = credential

    async def complete(
        self, candidate: CandidateSpec, case: TestCase, repetition: int
    ) -> ProviderResponse:
        parameters = dict(candidate.parameters)
        if {"model", "input", "store"}.intersection(parameters):
            raise ProviderError("reserved Responses parameter", kind="configuration")
        aliases = [name for name in ("max_tokens", "max_completion_tokens") if name in parameters]
        if len(aliases) > 1:
            raise ProviderError("ambiguous Responses token limit", kind="configuration")
        if aliases:
            value = parameters.pop(aliases[0])
            if "max_output_tokens" in parameters and parameters["max_output_tokens"] != value:
                raise ProviderError("conflicting Responses token limit", kind="configuration")
            parameters["max_output_tokens"] = value

        payload = {
            "model": candidate.model,
            "input": [message.model_dump(exclude_none=True) for message in case.request.messages],
            "store": False,
            **parameters,
        }
        headers = {"Authorization": f"Bearer {self.credential}"} if self.credential else {}
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                response = await client.post(
                    "https://api.openai.com/v1/responses", json=payload, headers=headers
                )
            if response.is_error or response.is_redirect:
                error = provider_error_from_response(response, provider="openai")
                # Quota/billing exhaustion is not resolved by retrying a 429.
                if response.status_code == 429:
                    try:
                        remote_error = response.json().get("error")
                        code = remote_error.get("code") if isinstance(remote_error, dict) else None
                    except (ValueError, AttributeError):
                        code = None
                    if isinstance(code, str) and code in (
                        "insufficient_quota",
                        "billing_hard_limit_reached",
                    ):
                        error.retryable = False
                raise error
            try:
                data = response.json()
                if not isinstance(data, dict) or data.get("status") == "incomplete":
                    raise ValueError
                output = data["output"]
                if not isinstance(output, list):
                    raise ValueError
                texts = []
                for item in output:
                    if not isinstance(item, dict):
                        raise ValueError
                    if item.get("type") != "message":
                        continue
                    content = item.get("content")
                    if not isinstance(content, list):
                        raise ValueError
                    for block in content:
                        if not isinstance(block, dict):
                            raise ValueError
                        if block.get("type") == "output_text":
                            text = block.get("text")
                            if not isinstance(text, str):
                                raise ValueError
                            texts.append(text)
                raw_output = "".join(texts)
                if not raw_output:
                    raise ValueError
            except (ValueError, KeyError, TypeError):
                raise ProviderError("unusable Responses output", kind="response") from None

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
            details = usage.get("output_tokens_details")
            reasoning_tokens = (
                nonnegative_token_count(details.get("reasoning_tokens"))
                if isinstance(details, dict)
                else None
            )
            reasoning_texts = []
            for item in native["output"]:
                if item.get("type") != "reasoning":
                    continue
                for field, block_type in (
                    ("content", "reasoning_text"),
                    ("summary", "summary_text"),
                ):
                    blocks = item.get(field)
                    if isinstance(blocks, list):
                        texts = [
                            block["text"]
                            for block in blocks
                            if isinstance(block, dict)
                            and block.get("type") == block_type
                            and nonempty_string(block.get("text"))
                        ]
                        if texts:
                            reasoning_texts.extend(texts)
                            break
            native_status = nonempty_string(native.get("status"))

            return ProviderResponse(
                raw_output=raw_output,
                latency_ms=(time.perf_counter() - started) * 1000,
                input_tokens=token_count("input_tokens"),
                output_tokens=token_count("output_tokens"),
                total_tokens=token_count("total_tokens"),
                provider="openai",
                model=model,
                raw_response=native,
                finish_reason="stop" if native_status == "completed" else None,
                provider_finish_reason=native_status,
                provider_request_id=provider_request_id(response, self.credential),
                reasoning_tokens=reasoning_tokens,
                reasoning_content="\n\n".join(reasoning_texts) if reasoning_texts else None,
                usage_details=native_usage if isinstance(native_usage, dict) else None,
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
