from __future__ import annotations

import json
from pathlib import Path

from inferencefit.contracts import CandidateSpec, TestCase

from .base import ProviderError, ProviderResponse


class FixtureProvider:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self._cache: dict[Path, list[dict]] = {}

    def _records(self, path: Path) -> list[dict]:
        if path not in self._cache:
            self._cache[path] = [
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        return self._cache[path]

    async def complete(
        self, candidate: CandidateSpec, case: TestCase, repetition: int
    ) -> ProviderResponse:
        raw_path = candidate.parameters.get("fixture_path")
        if not raw_path:
            raise ProviderError("fixture candidate requires parameters.fixture_path")
        path = Path(raw_path)
        if not path.is_absolute():
            path = (self.base_dir / path).resolve()
        matches = [
            x
            for x in self._records(path)
            if x.get("case_id") == case.id and x.get("repetition", repetition) == repetition
        ]
        if not matches:
            raise ProviderError(f"no fixture response for case {case.id!r}")
        record = matches[0]
        if record.get("error"):
            raise ProviderError(str(record["error"]), retryable=bool(record.get("retryable")))
        return ProviderResponse(
            raw_output=str(record["raw_output"]),
            latency_ms=float(record.get("latency_ms", 0)),
            input_tokens=record.get("input_tokens"),
            output_tokens=record.get("output_tokens"),
            provider="fixture",
            model=candidate.model,
        )
