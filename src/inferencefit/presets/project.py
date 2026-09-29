"""Safe materialization of built-in workload preset projects."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from inferencefit.dataset import load_jsonl_dataset
from inferencefit.spec import load_evaluation_spec

from . import get_preset

__all__ = ["PresetDestinationError", "initialize_project"]

_TEMPLATE_ROOT = Path(__file__).with_name("templates")


class PresetDestinationError(ValueError):
    """Raised when a preset destination cannot be safely created."""


def _copy_template(source: Path, destination: Path) -> None:
    if source.is_symlink():
        raise RuntimeError(f"preset template must not be a symlink: {source}")
    if not source.is_dir():
        raise RuntimeError(f"preset template directory is missing: {source}")

    entries = sorted(source.rglob("*"), key=lambda path: path.relative_to(source).as_posix())
    for entry in entries:
        relative = entry.relative_to(source)
        target = destination / relative
        if entry.is_symlink():
            raise RuntimeError(f"preset template contains a symlink: {relative.as_posix()}")
        if entry.is_dir():
            target.mkdir()
        elif entry.is_file():
            shutil.copy2(entry, target)
        else:
            raise RuntimeError(
                f"preset template contains a non-regular entry: {relative.as_posix()}"
            )


def initialize_project(preset_id: str, destination: str | Path) -> tuple[Path, ...]:
    """Copy and validate one built-in preset without overwriting existing paths."""

    preset = get_preset(preset_id)
    template = _TEMPLATE_ROOT / preset.template_name
    target = Path(destination).expanduser().absolute()

    if os.path.lexists(target):
        raise PresetDestinationError(f"destination already exists: {target}")
    if not target.parent.exists():
        raise PresetDestinationError(f"destination parent does not exist: {target.parent}")
    if not target.parent.is_dir():
        raise PresetDestinationError(f"destination parent is not a directory: {target.parent}")

    target.mkdir()
    try:
        _copy_template(template, target)
        loaded = load_evaluation_spec(target / "eval.yaml")
        load_jsonl_dataset(loaded.resolve_dataset_path())
        return tuple(
            sorted(
                (path for path in target.rglob("*") if path.is_file()),
                key=lambda path: path.relative_to(target).as_posix(),
            )
        )
    except Exception:
        shutil.rmtree(target)
        raise
