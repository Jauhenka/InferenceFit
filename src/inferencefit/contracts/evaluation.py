"""Top-level EvaluationSpec public contract."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .candidates import CandidateSpec
from .common import SCHEMA_VERSION, validate_schema_version
from .dataset import DatasetRef
from .execution import ExecutionSpec
from .optimization import ConstraintSpec, OptimizationSpec
from .validators import ValidatorSpec


class EvaluationSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    dataset: DatasetRef
    candidates: list[CandidateSpec]
    validators: list[ValidatorSpec] = Field(default_factory=list)
    constraints: list[ConstraintSpec] = Field(default_factory=list)
    optimization: OptimizationSpec = Field(default_factory=OptimizationSpec)
    execution: ExecutionSpec = Field(default_factory=ExecutionSpec)

    @model_validator(mode="before")
    @classmethod
    def _raw_unique_constraints(cls, value):
        if isinstance(value, dict) and isinstance(value.get("constraints"), dict):
            converted = dict(value)
            converted["constraints"] = [
                {"id": name, "metric": name, "threshold": threshold}
                for name, threshold in value["constraints"].items()
            ]
            value = converted
        if isinstance(value, dict) and isinstance(value.get("constraints"), list):
            ids = [item.get("id") for item in value["constraints"] if isinstance(item, dict)]
            cls._unique(ids, "constraint")
        return value

    @field_validator("schema_version")
    @classmethod
    def _schema(cls, value: str) -> str:
        return validate_schema_version(value)

    @field_validator("candidates")
    @classmethod
    def _candidates(cls, value: list[CandidateSpec]) -> list[CandidateSpec]:
        if not value:
            raise ValueError("at least one candidate is required")
        cls._unique([item.id for item in value], "candidate")
        return value

    @field_validator("validators")
    @classmethod
    def _validators(cls, value: list[ValidatorSpec]) -> list[ValidatorSpec]:
        cls._unique([item.id for item in value], "validator")
        return value

    @field_validator("constraints")
    @classmethod
    def _constraints(cls, value: list[ConstraintSpec]) -> list[ConstraintSpec]:
        cls._unique([item.id for item in value], "constraint")
        return value

    @staticmethod
    def _unique(values: list[str], label: str) -> None:
        if len(values) != len(set(values)):
            raise ValueError(f"{label} ids must be unique")

    @model_validator(mode="after")
    def _cascade_candidates(self) -> EvaluationSpec:
        cascade = self.optimization.cascade
        if cascade is None:
            return self
        ids = {item.id for item in self.candidates}
        refs = [cascade.primary, *cascade.fallbacks]
        if (
            len(cascade.fallbacks) != len(set(cascade.fallbacks))
            or cascade.primary in cascade.fallbacks
        ):
            raise ValueError("cascade candidate ids must be unique")
        missing = [item for item in refs if item not in ids]
        if missing:
            raise ValueError(f"cascade references unknown candidate {missing[0]!r}")
        return self
