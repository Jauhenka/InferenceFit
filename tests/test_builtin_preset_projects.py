"""Integration tests for the three bundled, offline-runnable preset projects."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from inferencefit import benchmark
from inferencefit.dataset import load_jsonl_dataset
from inferencefit.presets import list_presets
from inferencefit.presets.project import initialize_project
from inferencefit.spec import load_evaluation_spec

EXPECTED_FILES = {
    "README.md",
    "cases.jsonl",
    "eval.yaml",
    "fixtures/sample.jsonl",
}
PRODUCTION_WARNING = (
    "Replace the sample cases with representative production examples before using the "
    "benchmark for model-selection decisions."
)
LIVE_EXAMPLE_IDENTIFIERS = {
    "accounts/fireworks/models/nemotron-lightning-3p5-30b-a3b",
    "deepseek-flash",
    "gemini-3.5-flash-lite",
    "gpt-6-luna",
    "openrouter/free",
}
SECRET_ASSIGNMENT = re.compile(
    r"(?i)(?:api[_-]?key|access[_-]?token|secret|password)\s*[:=]\s*[\"'][^\"']+[\"']"
)


def _relative_files(project: Path) -> set[str]:
    return {
        path.relative_to(project).as_posix()
        for path in project.rglob("*")
        if path.is_file()
    }


@pytest.mark.parametrize("preset", list_presets(), ids=lambda preset: preset.identifier)
def test_builtin_preset_has_valid_minimal_project(preset, tmp_path: Path) -> None:
    project = tmp_path / preset.identifier

    created = initialize_project(preset.identifier, project)

    assert _relative_files(project) == EXPECTED_FILES
    assert {path.relative_to(project).as_posix() for path in created} == EXPECTED_FILES
    loaded = load_evaluation_spec(project / "eval.yaml")
    dataset = load_jsonl_dataset(loaded.resolve_dataset_path())
    assert len(dataset) == 2
    assert [candidate.provider for candidate in loaded.spec.candidates] == ["fixture"]
    assert loaded.spec.execution.repetitions == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("preset", list_presets(), ids=lambda preset: preset.identifier)
async def test_builtin_preset_completes_offline_benchmark(preset, tmp_path: Path) -> None:
    project = tmp_path / preset.identifier
    initialize_project(preset.identifier, project)

    result = await benchmark(project / "eval.yaml", output_root=tmp_path / "runs")

    assert result.status == "completed"
    assert result.recommendation == "offline-fixture"
    assert len(result.candidate_summaries) == 1
    summary = result.candidate_summaries[0]
    assert summary.id == "offline-fixture"
    assert summary.planned_count == 2
    assert summary.provider_success_count == 2
    assert summary.provider_error_count == 0
    assert summary.validation_pass_count == 2


@pytest.mark.parametrize("preset", list_presets(), ids=lambda preset: preset.identifier)
def test_builtin_preset_contains_no_live_configuration_or_secret(preset, tmp_path: Path) -> None:
    project = tmp_path / preset.identifier
    initialize_project(preset.identifier, project)
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in project.rglob("*")
        if path.is_file()
    )

    assert SECRET_ASSIGNMENT.search(source) is None
    assert all(identifier not in source for identifier in LIVE_EXAMPLE_IDENTIFIERS)
    loaded = load_evaluation_spec(project / "eval.yaml")
    candidate = loaded.spec.candidates[0]
    assert candidate.provider == "fixture"
    assert candidate.credential_ref is None


@pytest.mark.parametrize(
    ("preset_id", "caveat_terms"),
    [
        (
            "coding",
            {"brittle", "trusted", "unit tests", "bounded", "untrusted"},
        ),
        (
            "document-processing",
            {
                "classification",
                "qa",
                "summarization",
                "synthesis",
                "long-input",
                "semantic",
            },
        ),
        (
            "structured-extraction",
            {"field-level", "numeric", "temperature", "supports"},
        ),
    ],
)
def test_builtin_preset_readme_explains_safe_customization(
    preset_id: str, caveat_terms: set[str], tmp_path: Path
) -> None:
    project = tmp_path / preset_id
    initialize_project(preset_id, project)
    readme = (project / "README.md").read_text(encoding="utf-8")
    lowered = readme.lower()

    assert readme.startswith(PRODUCTION_WARNING)
    assert "plumbing check" in lowered
    for term in {"cases", "candidate", "validator", "benchmark", "customiz", *caveat_terms}:
        assert term in lowered
