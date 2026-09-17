"""Candidate and pricing contracts."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PricingSpec(BaseModel):
    """Per-million-token prices for a candidate; ``None`` means unknown."""

    model_config = ConfigDict(extra="forbid")

    input_per_million: float | None = None
    output_per_million: float | None = None

    @field_validator("input_per_million", "output_per_million")
    @classmethod
    def _non_negative(cls, value: float | None) -> float | None:
        if value is not None and value < 0:
            raise ValueError("pricing values must be non-negative")
        return value


class CandidateSpec(BaseModel):
    """A single model configuration under evaluation."""

    model_config = ConfigDict(extra="forbid")

    id: str
    provider: str
    model: str
    base_url: str | None = None
    credential_ref: str | None = None
    pricing: PricingSpec | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _non_empty_id(cls, value: str) -> str:
        if not value:
            raise ValueError("candidate id must be a non-empty string")
        return value

    @field_validator("provider", "model")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("field must be a non-empty string")
        return value
