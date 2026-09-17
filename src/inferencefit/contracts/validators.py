"""Validator configuration contracts."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ValidatorType = Literal[
    "exact",
    "regex",
    "enum",
    "json_schema",
    "numeric",
    "contains",
    "python",
]

#: Validators that may only run after full evaluation and therefore cannot act
#: as a runtime routing gate.
EVAL_ONLY_VALIDATOR_TYPES: frozenset[str] = frozenset({"exact", "numeric", "python"})

#: Validators that can evaluate a raw model response at request time and may be
#: used as runtime routing gates.
RUNTIME_VALIDATOR_TYPES: frozenset[str] = frozenset({"regex", "enum", "json_schema", "contains"})

ALL_VALIDATOR_TYPES: frozenset[str] = EVAL_ONLY_VALIDATOR_TYPES | RUNTIME_VALIDATOR_TYPES


class ValidatorSpec(BaseModel):
    """Declarative configuration for a single validator instance."""

    model_config = ConfigDict(extra="forbid")

    id: str
    type: ValidatorType
    #: RFC 6901 pointer into the parsed model output. When set, the raw output
    #: is parsed as JSON before the value is read.
    target: str | None = None
    #: RFC 6901 pointer into ``TestCase.expected`` giving the reference value.
    reference: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    routing_gate: bool = False

    @model_validator(mode="after")
    def _runtime_gate_only(self) -> ValidatorSpec:
        if self.routing_gate and not self.runtime_capable:
            raise ValueError(f"validator type {self.type!r} cannot be a routing_gate")
        return self

    @field_validator("id")
    @classmethod
    def _non_empty_id(cls, value: str) -> str:
        if not value:
            raise ValueError("validator id must be a non-empty string")
        return value

    @property
    def eval_only(self) -> bool:
        return self.type in EVAL_ONLY_VALIDATOR_TYPES

    @property
    def runtime_capable(self) -> bool:
        return self.type in RUNTIME_VALIDATOR_TYPES
