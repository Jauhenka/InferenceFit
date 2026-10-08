from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from pydantic import JsonValue

from inferencefit.contracts import CandidateSpec, TestCase


@dataclass(frozen=True)
class ProviderResponse:
    raw_output: str
    latency_ms: float
    input_tokens: int | None = None
    output_tokens: int | None = None
    provider: str | None = None
    model: str | None = None
    total_tokens: int | None = None
    cost_usd: float | None = None
    provider_backend: str | None = None
    raw_response: JsonValue | None = None
    finish_reason: str | None = None
    provider_finish_reason: str | None = None
    provider_request_id: str | None = None
    reasoning_tokens: int | None = None
    reasoning_content: str | None = None
    usage_details: dict[str, JsonValue] | None = None


class ProviderError(Exception):
    def __init__(self, message: str, *, retryable: bool = False, kind: str = "provider_error"):
        super().__init__(message)
        self.retryable = retryable
        self.kind = kind


class ProviderAdapter(Protocol):
    async def complete(
        self, candidate: CandidateSpec, case: TestCase, repetition: int
    ) -> ProviderResponse: ...
