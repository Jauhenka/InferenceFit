"""Aggregated open result and routing contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .common import SCHEMA_VERSION


class ConstraintResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    metric: str
    passed: bool
    actual: float | None
    required: float
    comparison: str


class CandidateSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    kind: Literal["candidate", "cascade"] = "candidate"
    planned_count: int = 0
    provider_success_count: int = 0
    provider_error_count: int = 0
    provider_success_rate: float = 0.0
    provider_error_rate: float = 0.0
    validation_pass_count: int = 0
    validation_pass_rate: float = 0.0
    end_to_end_success_rate: float = 0.0
    mean_latency_ms: float | None = None
    p50_latency_ms: float | None = None
    p95_latency_ms: float | None = None
    total_cost_usd: float | None = None
    mean_cost_per_request_usd: float | None = None
    cost_per_1k_requests_usd: float | None = None
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    eligible: bool = True
    constraint_results: list[ConstraintResult] = Field(default_factory=list)
    failed_constraints: list[ConstraintResult] = Field(default_factory=list)
    objective_score: float | None = None
    unrankable_reason: str | None = None
    fallback_rate: float | None = None
    primary: str | None = None
    fallback: str | None = None


class RoutingPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str = SCHEMA_VERSION
    strategy: Literal["single", "fallback", "none"]
    candidate: str | None = None
    primary: str | None = None
    fallback: str | None = None
    fallback_on: dict[str, Any] | None = None
    reason: str | None = None


class ResultBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str = SCHEMA_VERSION
    run_id: str
    started_at: datetime
    completed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: Literal["completed", "cancelled", "failed"] = "completed"
    provenance: dict[str, Any]
    constraints: dict[str, float] = Field(default_factory=dict)
    candidate_summaries: list[CandidateSummary] = Field(default_factory=list)
    cascade_summaries: list[CandidateSummary] = Field(default_factory=list)
    pareto_frontier: list[str] = Field(default_factory=list)
    objective: str
    formula_version: str | None = None
    recommendation: str | None = None
    ranking: list[str] = Field(default_factory=list)
    recommendation_reason: str
    routing_policy: RoutingPolicy | None = None
