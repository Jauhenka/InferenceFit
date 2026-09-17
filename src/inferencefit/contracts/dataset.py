"""Dataset and test-case contracts."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

Role = Literal["system", "user", "assistant"]

_ALLOWED_FORMATS = ("jsonl",)


class ChatMessage(BaseModel):
    """A single chat message in an OpenAI-compatible request."""

    model_config = ConfigDict(extra="forbid")

    role: Role
    content: str
    name: str | None = None


class RequestSpec(BaseModel):
    """The immutable request payload sent to a candidate for one case."""

    model_config = ConfigDict(extra="forbid")

    messages: list[ChatMessage]

    @field_validator("messages")
    @classmethod
    def _non_empty_messages(cls, value: list[ChatMessage]) -> list[ChatMessage]:
        if not value:
            raise ValueError("test case must contain at least one message")
        return value


class TestCase(BaseModel):
    """One evaluation case: a chat request plus optional expected values.

    ``expected`` and ``metadata`` hold arbitrary JSON-compatible data and are
    never interpreted by the loader.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    request: RequestSpec
    expected: JsonValue = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def _non_empty_id(cls, value: str) -> str:
        if not value:
            raise ValueError("test case id must be a non-empty string")
        return value

    @field_validator("metadata", mode="before")
    @classmethod
    def _coerce_metadata(cls, value: Any) -> Any:
        if value is None:
            return {}
        return value


TestCase.__test__ = False


class DatasetRef(BaseModel):
    """A pointer to the dataset consumed by an evaluation spec."""

    model_config = ConfigDict(extra="forbid")

    path: str
    format: Literal["jsonl"] = "jsonl"

    @field_validator("path")
    @classmethod
    def _non_empty_path(cls, value: str) -> str:
        if not value:
            raise ValueError("dataset path must be a non-empty string")
        return value
