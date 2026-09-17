from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

import yaml

from inferencefit.contracts import Observation


class FilesystemArtifactStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def run_dir(self, run_id: str) -> Path:
        valid = re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", run_id)
        if run_id in {".", ".."} or valid is None:
            raise ValueError("run_id must contain only letters, digits, '.', '_' and '-'")
        return self.root / run_id

    def create(self, run_id: str) -> Path:
        path = self.run_dir(run_id)
        path.mkdir(parents=True, exist_ok=False)
        return path

    def atomic_json(self, path: Path, value) -> None:
        self._atomic_text(path, json.dumps(value, indent=2, sort_keys=True, default=str) + "\n")

    def atomic_yaml(self, path: Path, value) -> None:
        self._atomic_text(path, yaml.safe_dump(value, sort_keys=False))

    def _atomic_text(self, path: Path, text: str) -> None:
        fd, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(text)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, path)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def append_observation(self, run_id: str, observation: Observation) -> None:
        with (self.run_dir(run_id) / "observations.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(observation.model_dump_json() + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    def observations(self, run_id: str) -> list[Observation]:
        path = self.run_dir(run_id) / "observations.jsonl"
        if not path.exists():
            return []
        return [
            Observation.model_validate_json(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
