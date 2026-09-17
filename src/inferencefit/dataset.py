"""JSONL dataset loading and stable provenance hashing."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path

from pydantic import ValidationError

from .contracts.dataset import TestCase
from .errors import DatasetError


class Dataset(Sequence[TestCase]):
    def __init__(self, cases: Iterable[TestCase]):
        self.cases = tuple(cases)
        self.sha256 = dataset_sha256(self.cases)

    def __len__(self) -> int:
        return len(self.cases)

    def __getitem__(self, index):
        return self.cases[index]

    def __iter__(self) -> Iterator[TestCase]:
        return iter(self.cases)


def dataset_sha256(cases: Iterable[TestCase]) -> str:
    digest = hashlib.sha256()
    for case in cases:
        line = json.dumps(case.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        digest.update(line.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def load_jsonl_dataset(path: str | Path) -> Dataset:
    cases: list[TestCase] = []
    seen: set[str] = set()
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise DatasetError(f"cannot read dataset {path}: {exc}") from exc
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
            if not isinstance(raw, dict):
                raise DatasetError(f"line {number} must be a JSON object")
            case = TestCase.model_validate(raw)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise DatasetError(f"invalid dataset line {number}: {exc}") from exc
        if case.id in seen:
            raise DatasetError(f"duplicate test case id {case.id!r} on line {number}")
        seen.add(case.id)
        cases.append(case)
    return Dataset(cases)
