"""EvaluationSpec YAML/JSON loading."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import ValidationError

from .contracts.evaluation import EvaluationSpec
from .errors import SpecLoadError


class UniqueKeyLoader(yaml.SafeLoader):
    pass


def _mapping(loader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise SpecLoadError(f"duplicate YAML key {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


@dataclass(frozen=True)
class LoadedEvaluationSpec:
    spec: EvaluationSpec
    source_path: Path

    def resolve_dataset_path(self) -> Path:
        path = Path(self.spec.dataset.path)
        return path if path.is_absolute() else (self.source_path.parent / path).resolve()


def load_evaluation_spec(path: str | Path) -> LoadedEvaluationSpec:
    source = Path(path).resolve()
    try:
        text = source.read_text(encoding="utf-8")
        raw = (
            json.loads(text)
            if source.suffix.lower() == ".json"
            else yaml.load(text, Loader=UniqueKeyLoader)
        )
        if not isinstance(raw, dict):
            raise SpecLoadError("evaluation spec must be an object")
        return LoadedEvaluationSpec(EvaluationSpec.model_validate(raw), source)
    except SpecLoadError:
        raise
    except (OSError, json.JSONDecodeError, yaml.YAMLError, ValidationError, ValueError) as exc:
        raise SpecLoadError(f"invalid evaluation spec {source}: {exc}") from exc
