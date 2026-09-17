"""Focused tests for the RFC 6901 JSON Pointer utility."""

from __future__ import annotations

import pytest

from inferencefit.errors import JsonPointerError
from inferencefit.json_pointer import resolve_pointer


def test_empty_pointer_returns_root_document() -> None:
    document = {"a": [1, 2, 3]}
    assert resolve_pointer(document, "") is document


def test_object_key_resolution() -> None:
    document = {"a": {"b": 42}}
    assert resolve_pointer(document, "/a/b") == 42


def test_root_level_object_key() -> None:
    document = {"hello": "world"}
    assert resolve_pointer(document, "/hello") == "world"


def test_array_index_resolution() -> None:
    document = {"items": ["a", "b", "c"]}
    assert resolve_pointer(document, "/items/0") == "a"
    assert resolve_pointer(document, "/items/2") == "c"


def test_nested_array_resolution() -> None:
    document = [{"values": [10, 20]}]
    assert resolve_pointer(document, "/0/values/1") == 20


def test_escaped_slash_in_object_key() -> None:
    document = {"a/b": {"c~d": 7}}
    assert resolve_pointer(document, "/a~1b/c~0d") == 7


def test_empty_object_key() -> None:
    document = {"": "empty-key"}
    assert resolve_pointer(document, "/") == "empty-key"


def test_missing_object_key_is_explicit() -> None:
    with pytest.raises(JsonPointerError, match="missing key"):
        resolve_pointer({"a": 1}, "/b")


def test_missing_array_index_is_explicit() -> None:
    with pytest.raises(JsonPointerError, match="out of range"):
        resolve_pointer([1], "/2")


def test_invalid_array_index_is_explicit() -> None:
    with pytest.raises(JsonPointerError, match="array index"):
        resolve_pointer([1], "/x")


def test_leading_zero_array_index_is_explicit() -> None:
    with pytest.raises(JsonPointerError, match="array index"):
        resolve_pointer([1, 2], "/01")


def test_array_dash_is_not_a_pointer_index() -> None:
    with pytest.raises(JsonPointerError, match="array index"):
        resolve_pointer([1, 2], "/-")


def test_invalid_escape_sequence_is_explicit() -> None:
    with pytest.raises(JsonPointerError, match="escape"):
        resolve_pointer({"a": 1}, "/a~2b")


def test_pointer_must_start_with_slash() -> None:
    with pytest.raises(JsonPointerError, match="must be empty or start with"):
        resolve_pointer({"a": 1}, "a")


def test_cannot_descend_into_scalar() -> None:
    with pytest.raises(JsonPointerError, match="scalar"):
        resolve_pointer({"a": 1}, "/a/b")
