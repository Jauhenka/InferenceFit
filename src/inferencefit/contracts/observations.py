"""Terminal planned-evaluation observations."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .common import SCHEMA_VERSION
from .validation import ValidationSummary


class TokenUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input_tokens: int | None = None
    output_tokens: int | None = None


class ObservationError(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str
    message: str
    retryable: bool = False


class Observation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str = SCHEMA_VERSION
    case_id: str
    candidate_id: str
    repetition: int
    provider_status: Literal["success", "error", "cancelled"]
    raw_output: str | None = None
    parsed_output: Any = None
    usage: TokenUsage = Field(default_factory=TokenUsage)
    latency_ms: float | None = None
    cost_usd: float | None = None
    provider_attempts: int = 1
    validation: ValidationSummary | None = None
    error: ObservationError | None = None

    @property
    def identity(self) -> tuple[str, str, int]:
        return (self.case_id, self.candidate_id, self.repetition)
