"""Validation result contracts."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ValidationResult(BaseModel):
    """Structured outcome of running a single validator against one output.

    Failures are represented as data (``passed=False``) rather than raised
    exceptions so that they can be persisted and aggregated.
    """

    model_config = ConfigDict(extra="forbid")

    validator_id: str
    passed: bool
    observed: Any = None
    expected: Any = None
    message: str | None = None
    structured: bool = False
    details: dict[str, Any] = Field(default_factory=dict)
    runtime_capable: bool = False


class ValidationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: bool
    results: list[ValidationResult] = Field(default_factory=list)


class CandidateResponse(BaseModel):
    """Normalized response exposed to local Python validators."""

    model_config = ConfigDict(extra="forbid")
    raw_output: str
    parsed_output: Any = None
