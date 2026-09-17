from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from inferencefit.contracts import CandidateSpec, TestCase


@dataclass(frozen=True)
class ProviderResponse:
    raw_output: str
    latency_ms: float
    input_tokens: int | None = None
    output_tokens: int | None = None
    provider: str | None = None
    model: str | None = None


class ProviderError(Exception):
    def __init__(self, message: str, *, retryable: bool = False, kind: str = "provider_error"):
        super().__init__(message)
        self.retryable = retryable
        self.kind = kind


class ProviderAdapter(Protocol):
    async def complete(
        self, candidate: CandidateSpec, case: TestCase, repetition: int
    ) -> ProviderResponse: ...
