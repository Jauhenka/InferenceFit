from __future__ import annotations

import json
from pathlib import Path

import pytest

from inferencefit.dataset import load_jsonl_dataset
from inferencefit.errors import DatasetError, SpecLoadError
from inferencefit.presets import UnknownPresetError
from inferencefit.presets import project as project_module
from inferencefit.presets.project import PresetDestinationError, initialize_project
from inferencefit.spec import load_evaluation_spec


def _write_template(
    root: Path, *, invalid_spec: bool = False, invalid_dataset: bool = False
) -> None:
    template = root / "coding"
    (template / "fixtures").mkdir(parents=True)
    (template / "README.md").write_text("# Coding preset\n", encoding="utf-8")
    (template / "cases.jsonl").write_text(
        "not-json\n"
        if invalid_dataset
        else json.dumps(
            {
                "id": "case-1",
                "request": {"messages": [{"role": "user", "content": "Return JSON."}]},
                "expected": {"code": "ok"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (template / "fixtures" / "sample.jsonl").write_text(
        json.dumps({"case_id": "case-1", "raw_output": '{"code":"ok"}'}) + "\n",
        encoding="utf-8",
    )
    (template / "eval.yaml").write_text(
        "not: [valid"
        if invalid_spec
        else """schema_version: "0.1"
dataset:
  path: cases.jsonl
candidates:
  - id: sample-baseline
    provider: fixture
    model: sample-fixture
    parameters:
      fixture_path: fixtures/sample.jsonl
validators:
  - id: exact-code
    type: exact
    target: /code
    reference: /code
""",
        encoding="utf-8",
    )


@pytest.fixture
def template_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "templates"
    _write_template(root)
    monkeypatch.setattr(project_module, "_TEMPLATE_ROOT", root)
    return root


def test_initialize_project_copies_and_validates_template(
    tmp_path: Path, template_root: Path
) -> None:
    destination = tmp_path / "project"

    created = initialize_project("coding", destination)

    assert [path.relative_to(destination).as_posix() for path in created] == [
        "README.md",
        "cases.jsonl",
        "eval.yaml",
        "fixtures/sample.jsonl",
    ]
    loaded = load_evaluation_spec(destination / "eval.yaml")
    assert len(load_jsonl_dataset(loaded.resolve_dataset_path())) == 1


@pytest.mark.parametrize("kind", ["file", "directory"])
def test_initialize_project_never_overwrites_existing_destination(
    tmp_path: Path, template_root: Path, kind: str
) -> None:
    destination = tmp_path / "project"
    if kind == "file":
        destination.write_text("keep me", encoding="utf-8")
    else:
        destination.mkdir()
        (destination / "keep.txt").write_text("keep me", encoding="utf-8")

    with pytest.raises(PresetDestinationError, match="already exists"):
        initialize_project("coding", destination)

    kept = destination if kind == "file" else destination / "keep.txt"
    assert kept.read_text(encoding="utf-8") == "keep me"


def test_initialize_project_treats_dangling_symlink_as_conflict(
    tmp_path: Path, template_root: Path
) -> None:
    destination = tmp_path / "project"
    try:
        destination.symlink_to(tmp_path / "missing-target", target_is_directory=True)
    except OSError as error:
        pytest.skip(f"symlinks unavailable: {error}")

    with pytest.raises(PresetDestinationError, match="already exists"):
        initialize_project("coding", destination)

    assert destination.is_symlink()


def test_initialize_project_requires_existing_directory_parent(
    tmp_path: Path, template_root: Path
) -> None:
    missing_parent = tmp_path / "missing" / "project"
    parent_file = tmp_path / "parent-file"
    parent_file.write_text("not a directory", encoding="utf-8")

    with pytest.raises(PresetDestinationError, match="parent.*does not exist"):
        initialize_project("coding", missing_parent)
    with pytest.raises(PresetDestinationError, match="parent.*not a directory"):
        initialize_project("coding", parent_file / "project")

    assert not missing_parent.parent.exists()


def test_initialize_project_propagates_unknown_preset(tmp_path: Path) -> None:
    with pytest.raises(UnknownPresetError, match="unknown preset 'missing'"):
        initialize_project("missing", tmp_path / "project")


def test_initialize_project_cleans_destination_after_copy_failure(
    tmp_path: Path, template_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "project"

    def fail_copy(source: Path, target: Path) -> None:
        (target / "partial.txt").write_text("partial", encoding="utf-8")
        raise OSError("copy failed")

    monkeypatch.setattr(project_module, "_copy_template", fail_copy)

    with pytest.raises(OSError, match="copy failed"):
        initialize_project("coding", destination)

    assert not destination.exists()


@pytest.mark.parametrize("failure", ["spec", "dataset"])
def test_initialize_project_cleans_destination_after_contract_validation_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    root = tmp_path / "templates"
    _write_template(
        root,
        invalid_spec=failure == "spec",
        invalid_dataset=failure == "dataset",
    )
    monkeypatch.setattr(project_module, "_TEMPLATE_ROOT", root)
    destination = tmp_path / "project"

    expected_error = SpecLoadError if failure == "spec" else DatasetError
    with pytest.raises(expected_error):
        initialize_project("coding", destination)

    assert not destination.exists()


def test_initialize_project_rejects_symlink_in_template(
    tmp_path: Path, template_root: Path
) -> None:
    link = template_root / "coding" / "linked.txt"
    try:
        link.symlink_to(template_root / "coding" / "README.md")
    except OSError as error:
        pytest.skip(f"symlinks unavailable: {error}")
    destination = tmp_path / "project"

    with pytest.raises(RuntimeError, match="symlink"):
        initialize_project("coding", destination)

    assert not destination.exists()
