"""Constraint, objective, and cascade optimization contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ObjectiveName = Literal["min_cost", "min_latency", "max_quality", "max_reliability", "balanced"]

ConstraintMetric = Literal[
    "min_success_rate",
    "max_p95_latency_ms",
    "max_cost_per_1k_requests_usd",
    "max_provider_error_rate",
    "max_cost_usd",
    "max_error_rate",
]


class ConstraintSpec(BaseModel):
    """A single hard constraint applied to candidate summaries."""

    model_config = ConfigDict(extra="forbid")

    id: str
    metric: ConstraintMetric
    threshold: float

    @field_validator("id")
    @classmethod
    def _non_empty_id(cls, value: str) -> str:
        if not value:
            raise ValueError("constraint id must be a non-empty string")
        return value

    @field_validator("threshold")
    @classmethod
    def _valid_threshold(cls, value: float, info):
        metric = info.data.get("metric")
        if metric in {"min_success_rate", "max_provider_error_rate", "max_error_rate"}:
            if not 0 <= value <= 1:
                raise ValueError("rate threshold must be between 0 and 1")
        elif value < 0:
            raise ValueError("threshold must be non-negative")
        return value


class CascadeSpec(BaseModel):
    """A two-stage primary/fallback cascade of candidate ids."""

    model_config = ConfigDict(extra="forbid")

    primary: str
    fallbacks: list[str] = Field(default_factory=list)

    @field_validator("primary")
    @classmethod
    def _non_empty_primary(cls, value: str) -> str:
        if not value:
            raise ValueError("cascade primary must be a non-empty string")
        return value

    @field_validator("fallbacks")
    @classmethod
    def _single_fallback(cls, value: list[str]) -> list[str]:
        if len(value) > 1:
            raise ValueError("E0 supports one fallback in a two-stage cascade")
        return value


class OptimizationSpec(BaseModel):
    """Deterministic ranking configuration."""

    model_config = ConfigDict(extra="forbid")

    objective: ObjectiveName = "balanced"
    cascade: CascadeSpec | None = None
