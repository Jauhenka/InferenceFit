"""Focused tests for the JSONL dataset loader and canonical hash."""

from __future__ import annotations

import json

import pytest

from inferencefit.contracts.dataset import TestCase
from inferencefit.dataset import Dataset, dataset_sha256, load_jsonl_dataset
from inferencefit.errors import DatasetError


def write_jsonl(path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def test_loads_arbitrary_expected_and_metadata(tmp_path) -> None:
    dataset_path = tmp_path / "cases.jsonl"
    write_jsonl(
        dataset_path,
        [
            json.dumps(
                {
                    "id": "case-1",
                    "request": {"messages": [{"role": "user", "content": "hello"}]},
                    "expected": {"label": "greeting", "confidence": 0.95},
                    "metadata": {"group": "unit", "tags": ["a", "b"]},
                }
            ),
            json.dumps(
                {
                    "id": "case-2",
                    "request": {
                        "messages": [
                            {"role": "system", "content": "be brief"},
                            {"role": "user", "content": "what is 1+1?"},
                        ]
                    },
                    "expected": [2, "two"],
                    "metadata": None,
                }
            ),
        ],
    )

    dataset = load_jsonl_dataset(dataset_path)

    assert isinstance(dataset, Dataset)
    assert len(dataset) == 2
    assert [case.id for case in dataset] == ["case-1", "case-2"]
    assert dataset[0].expected == {"label": "greeting", "confidence": 0.95}
    assert dataset[1].expected == [2, "two"]
    assert dataset[1].metadata == {}


def test_loaded_case_public_serialization_shape(tmp_path) -> None:
    dataset_path = tmp_path / "cases.jsonl"
    write_jsonl(
        dataset_path,
        [
            json.dumps(
                {
                    "id": "case-1",
                    "request": {"messages": [{"role": "user", "content": "hello"}]},
                    "expected": {"ok": True},
                    "metadata": {"n": 1},
                }
            )
        ],
    )

    case = load_jsonl_dataset(dataset_path)[0]

    dumped = case.model_dump(mode="json")
    assert set(dumped) == {"id", "request", "expected", "metadata"}
    assert "messages" not in dumped
    assert set(dumped["request"]) == {"messages"}
    assert dumped["request"]["messages"][0]["role"] == "user"


def test_rejects_duplicate_ids(tmp_path) -> None:
    dataset_path = tmp_path / "cases.jsonl"
    write_jsonl(
        dataset_path,
        [
            json.dumps(
                {
                    "id": "dup",
                    "request": {"messages": [{"role": "user", "content": "a"}]},
                }
            ),
            json.dumps(
                {
                    "id": "dup",
                    "request": {"messages": [{"role": "user", "content": "b"}]},
                }
            ),
        ],
    )

    with pytest.raises(DatasetError, match="duplicate"):
        load_jsonl_dataset(dataset_path)


def test_rejects_malformed_json_with_line_number(tmp_path) -> None:
    dataset_path = tmp_path / "cases.jsonl"
    write_jsonl(dataset_path, ['{"id": "x", "request": {"messages": []}', ""])

    with pytest.raises(DatasetError, match="line 1"):
        load_jsonl_dataset(dataset_path)


def test_rejects_invalid_case_shape(tmp_path) -> None:
    dataset_path = tmp_path / "cases.jsonl"
    write_jsonl(dataset_path, [json.dumps({"id": "no-request"})])

    with pytest.raises(DatasetError, match="line 1"):
        load_jsonl_dataset(dataset_path)


def test_rejects_non_object_jsonl_record(tmp_path) -> None:
    dataset_path = tmp_path / "cases.jsonl"
    write_jsonl(dataset_path, ["[1, 2, 3]"])

    with pytest.raises(DatasetError, match="object"):
        load_jsonl_dataset(dataset_path)


def test_skips_blank_lines(tmp_path) -> None:
    dataset_path = tmp_path / "cases.jsonl"
    write_jsonl(
        dataset_path,
        [
            "",
            json.dumps(
                {
                    "id": "case-1",
                    "request": {"messages": [{"role": "user", "content": "hello"}]},
                }
            ),
            "   ",
        ],
    )

    dataset = load_jsonl_dataset(dataset_path)
    assert [case.id for case in dataset] == ["case-1"]


def test_canonical_hash_is_stable_across_serialization_order(tmp_path) -> None:
    case = TestCase.model_validate(
        {
            "id": "case-1",
            "request": {"messages": [{"role": "user", "content": "hello"}]},
            "expected": {"b": 2, "a": 1},
            "metadata": {"z": [1, 2], "y": {"k": "v"}},
        }
    )

    first = dataset_sha256([case])
    second = dataset_sha256([case])

    assert first == second
    assert len(first) == 64
    assert isinstance(first, str)

    # Same logical content loaded from differently-formatted JSONL hashes the same.
    case_b = TestCase.model_validate(
        {
            "id": "case-1",
            "metadata": {"y": {"k": "v"}, "z": [1, 2]},
            "expected": {"a": 1, "b": 2},
            "request": {"messages": [{"role": "user", "content": "hello"}]},
        }
    )
    assert dataset_sha256([case_b]) == first


def test_canonical_hash_changes_with_content() -> None:
    case = TestCase.model_validate(
        {
            "id": "case-1",
            "request": {"messages": [{"role": "user", "content": "hello"}]},
        }
    )
    other = TestCase.model_validate(
        {
            "id": "case-2",
            "request": {"messages": [{"role": "user", "content": "hello"}]},
        }
    )
    assert dataset_sha256([case]) != dataset_sha256([other])


def test_empty_dataset_has_stable_hash(tmp_path) -> None:
    dataset_path = tmp_path / "empty.jsonl"
    dataset_path.write_text("", encoding="utf-8")

    dataset = load_jsonl_dataset(dataset_path)
    assert len(dataset) == 0
    assert dataset.sha256 == dataset_sha256([])
