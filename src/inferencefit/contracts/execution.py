"""Execution and retry contracts."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class RetrySpec(BaseModel):
    """Bounded exponential backoff for retryable provider failures."""

    model_config = ConfigDict(extra="forbid")

    max_attempts: int = 3
    initial_backoff_ms: int = 500
    max_backoff_ms: int = 5000

    @field_validator("max_attempts")
    @classmethod
    def _at_least_one(cls, value: int) -> int:
        if value < 1:
            raise ValueError("max_attempts must be >= 1")
        return value

    @field_validator("initial_backoff_ms", "max_backoff_ms")
    @classmethod
    def _non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("backoff settings must be non-negative")
        return value

    @model_validator(mode="after")
    def _ordered_backoff(self) -> RetrySpec:
        if self.max_backoff_ms < self.initial_backoff_ms:
            raise ValueError("max_backoff_ms must be >= initial_backoff_ms")
        return self


class ExecutionSpec(BaseModel):
    """Bounded, deterministic execution settings."""

    model_config = ConfigDict(extra="forbid")

    concurrency: int = 4
    timeout_ms: int = 30000
    repetitions: int = 1
    retry: RetrySpec = Field(default_factory=RetrySpec)

    @field_validator("concurrency", "repetitions")
    @classmethod
    def _at_least_one(cls, value: int) -> int:
        if value < 1:
            raise ValueError("value must be >= 1")
        return value

    @field_validator("timeout_ms")
    @classmethod
    def _positive_timeout(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("timeout_ms must be > 0")
        return value
