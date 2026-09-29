"""CLI contract tests for preset discovery and project initialization."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

import inferencefit.cli as cli_module
from inferencefit.cli import app
from inferencefit.presets.project import PresetDestinationError

runner = CliRunner()

EXPECTED_PRESET_LINES = [
    "coding: Code generation and transformation with deterministic checks.",
    "document-processing: Document classification and adaptable document-quality evaluation.",
    "structured-extraction: Schema-checked JSON extraction with exact expected fields.",
]

EXPECTED_RELATIVE_FILES = [
    "README.md",
    "cases.jsonl",
    "eval.yaml",
    "fixtures/sample.jsonl",
]

SAMPLE_WARNING = (
    "Replace the sample cases with representative production examples "
    "before using the benchmark for model-selection decisions."
)
CANDIDATE_WARNING = "Replace the fixture candidate with the models you actually want to evaluate."


def _resolved(destination: Path) -> Path:
    return Path(destination).expanduser().absolute()


def _make_stub_initializer(destination: Path):
    def stub(preset_id: str, target: str | Path) -> tuple[Path, ...]:
        base = _resolved(destination)
        created = []
        for relative in EXPECTED_RELATIVE_FILES:
            path = base / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("stub\n", encoding="utf-8")
            created.append(path)
        return tuple(created)

    return stub


def test_presets_prints_stable_lines_in_registry_order() -> None:
    result = runner.invoke(app, ["presets"])
    assert result.exit_code == 0
    assert result.stdout == "\n".join(EXPECTED_PRESET_LINES) + "\n"
    assert result.stderr == ""


def test_root_help_lists_presets_and_init() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "presets" in result.stdout
    assert "init" in result.stdout


def test_init_help_documents_option_and_argument() -> None:
    result = runner.invoke(app, ["init", "--help"])
    assert result.exit_code == 0
    assert "--preset" in result.stdout
    assert "DESTINATION" in result.stdout


def test_init_success_output(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    destination = tmp_path / "project"
    monkeypatch.setattr(cli_module, "initialize_project", _make_stub_initializer(destination))

    result = runner.invoke(app, ["init", "--preset", "coding", str(destination)])

    assert result.exit_code == 0
    resolved = _resolved(destination)
    assert str(resolved) in result.stdout
    for relative in EXPECTED_RELATIVE_FILES:
        assert relative in result.stdout
    assert SAMPLE_WARNING in result.stdout
    assert CANDIDATE_WARNING in result.stdout
    assert f"inferencefit benchmark {resolved / 'eval.yaml'}" in result.stdout
    assert result.stderr == ""


def test_init_unknown_preset_exits_two(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    destination = tmp_path / "project"

    result = runner.invoke(app, ["init", "--preset", "missing", str(destination)])

    assert result.exit_code == 2
    assert result.stdout == ""
    assert (
        "Unknown preset 'missing'. Run 'inferencefit presets' to list available presets."
        in result.stderr
    )
    assert "Traceback" not in result.stderr
    assert not destination.exists()


def test_init_existing_destination_exits_two(tmp_path: Path) -> None:
    destination = tmp_path / "existing"
    destination.mkdir()
    (destination / "keep.txt").write_text("keep\n", encoding="utf-8")

    result = runner.invoke(app, ["init", "--preset", "coding", str(destination)])

    assert result.exit_code == 2
    assert result.stdout == ""
    assert "already exists" in result.stderr
    assert "Traceback" not in result.stderr
    assert (destination / "keep.txt").read_text(encoding="utf-8") == "keep\n"


def test_init_invalid_parent_exits_two(tmp_path: Path) -> None:
    destination = tmp_path / "absent-parent" / "project"

    result = runner.invoke(app, ["init", "--preset", "coding", str(destination)])

    assert result.exit_code == 2
    assert result.stdout == ""
    assert str(_resolved(destination).parent) in result.stderr
    assert "Traceback" not in result.stderr
    assert not destination.exists()


def test_init_unexpected_failure_exits_one(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    destination = tmp_path / "project"

    def boom(preset_id: str, target: str | Path) -> tuple[Path, ...]:
        raise RuntimeError("preset template directory is missing")

    monkeypatch.setattr(cli_module, "initialize_project", boom)

    result = runner.invoke(app, ["init", "--preset", "coding", str(destination)])

    assert result.exit_code == 1
    assert result.stdout == ""
    assert "preset template directory is missing" in result.stderr
    assert "Traceback" not in result.stderr


def test_init_destination_error_is_still_reported(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    destination = tmp_path / "project"

    def conflict(preset_id: str, target: str | Path) -> tuple[Path, ...]:
        raise PresetDestinationError(f"destination already exists: {_resolved(destination)}")

    monkeypatch.setattr(cli_module, "initialize_project", conflict)

    result = runner.invoke(app, ["init", "--preset", "coding", str(destination)])

    assert result.exit_code == 2
    assert result.stdout == ""
    assert "already exists" in result.stderr
    assert "Traceback" not in result.stderr


EXPECTED_SKILL_REFERENCES = {
    "presets.md",
    "validators.md",
    "interpreting-results.md",
}


def test_root_help_lists_skill_command() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "skill" in result.stdout


def test_skill_help_lists_path_command() -> None:
    result = runner.invoke(app, ["skill", "--help"])
    assert result.exit_code == 0
    assert "path" in result.stdout


def test_skill_path_prints_one_absolute_directory() -> None:
    result = runner.invoke(app, ["skill", "path"])

    assert result.exit_code == 0
    assert result.stderr == ""

    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 1, f"expected exactly one printed path, got: {lines!r}"

    skill_dir = Path(lines[0].strip())
    assert skill_dir.is_absolute()
    assert skill_dir.is_dir()

    skill_file = skill_dir / "SKILL.md"
    assert skill_file.is_file()
    assert skill_file.read_text(encoding="utf-8").strip()

    references = skill_dir / "references"
    assert references.is_dir()
    assert {path.name for path in references.glob("*.md")} == EXPECTED_SKILL_REFERENCES
    for name in EXPECTED_SKILL_REFERENCES:
        assert (references / name).read_text(encoding="utf-8").strip()


def test_skill_path_matches_canonical_helper() -> None:
    from inferencefit.agent_skill import canonical_skill_path

    result = runner.invoke(app, ["skill", "path"])
    assert result.exit_code == 0
    assert result.stdout.strip() == str(canonical_skill_path().absolute())
