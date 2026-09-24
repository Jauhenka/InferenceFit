"""Structural contracts for the public continuous-integration workflow.

The CI workflow is parsed with :class:`yaml.BaseLoader` so that every scalar
(including the ``on`` trigger key, booleans, and version numbers) stays a
string.  The tests then make behaviour-focused assertions about the semantic
shape of the workflow rather than matching brittle whole-file text.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "ci.yml"

EXPECTED_MATRIX = {
    ("ubuntu-latest", "3.11"),
    ("ubuntu-latest", "3.12"),
    ("ubuntu-latest", "3.13"),
    ("windows-latest", "3.13"),
}

CURRENT_ACTION_MAJORS = {
    "actions/checkout": "v7",
    "actions/setup-python": "v7",
    "actions/upload-artifact": "v7",
}

FORBIDDEN_WORKFLOW_REFERENCES = (
    "secrets.",
    "inferencefit_live_tests",
    "api_key",
    "apikey",
    "credential",
    "password",
)


def load_workflow() -> dict[str, Any]:
    assert WORKFLOW_PATH.is_file(), f"missing workflow: {WORKFLOW_PATH}"
    loaded = yaml.load(WORKFLOW_PATH.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    assert isinstance(loaded, dict), "workflow root must be a mapping"
    return loaded


def job(workflow: dict[str, Any], name: str) -> dict[str, Any]:
    jobs = workflow["jobs"]
    assert name in jobs, f"workflow is missing the {name!r} job"
    return jobs[name]


def walk(node: Any) -> Iterator[Any]:
    """Yield every nested container in a parsed YAML document."""
    yield node
    if isinstance(node, dict):
        for value in node.values():
            yield from walk(value)
    elif isinstance(node, list):
        for item in node:
            yield from walk(item)


def strings(node: Any) -> Iterator[str]:
    if isinstance(node, dict):
        for key, value in node.items():
            yield str(key)
            yield from strings(value)
    elif isinstance(node, list):
        for item in node:
            yield from strings(item)
    elif isinstance(node, str):
        yield node


def step_commands(job_definition: dict[str, Any]) -> list[str]:
    return [
        step["run"]
        for step in job_definition.get("steps", [])
        if isinstance(step, dict) and "run" in step
    ]


def action_references(workflow: dict[str, Any]) -> list[str]:
    references = []
    for node in walk(workflow):
        if isinstance(node, dict) and isinstance(node.get("uses"), str):
            references.append(node["uses"])
    return references


def environment_mappings(workflow: dict[str, Any]) -> list[dict[str, str]]:
    mappings = []
    for node in walk(workflow):
        if isinstance(node, dict) and isinstance(node.get("env"), dict):
            mappings.append(node["env"])
    return mappings


def test_workflow_triggers_push_and_pull_request() -> None:
    workflow = load_workflow()
    triggers = workflow["on"]
    assert isinstance(triggers, dict), "on triggers must be a mapping"
    assert "push" in triggers
    assert "pull_request" in triggers


def test_workflow_declares_least_privilege_permissions() -> None:
    workflow = load_workflow()
    assert workflow.get("permissions") == {"contents": "read"}


def test_test_matrix_is_exactly_the_supported_combinations() -> None:
    workflow = load_workflow()
    test_job = job(workflow, "test")
    matrix = test_job["strategy"]["matrix"]
    entries = matrix["include"]
    combinations = {(entry["os"], entry["python"]) for entry in entries}
    assert len(entries) == len(EXPECTED_MATRIX)
    assert combinations == EXPECTED_MATRIX


def test_test_matrix_does_not_fail_fast() -> None:
    workflow = load_workflow()
    strategy = job(workflow, "test")["strategy"]
    assert strategy["fail-fast"] == "false"


def test_test_job_runs_pytest_on_the_matrix_runner() -> None:
    workflow = load_workflow()
    test_job = job(workflow, "test")
    assert test_job["runs-on"] == "${{ matrix.os }}"
    commands = step_commands(test_job)
    assert any("pytest" in command for command in commands), "test job must run pytest"

    setup_versions = [
        step.get("with", {}).get("python-version")
        for step in test_job.get("steps", [])
        if isinstance(step, dict) and str(step.get("uses", "")).startswith("actions/setup-python@")
    ]
    assert "${{ matrix.python }}" in setup_versions


def test_ordinary_tests_stay_offline_without_provider_credentials() -> None:
    workflow = load_workflow()
    test_job = job(workflow, "test")

    for command in step_commands(test_job):
        assert "INFERENCEFIT_LIVE_TESTS" not in command

    for value in strings(workflow):
        lowered = value.lower()
        assert not any(fragment in lowered for fragment in FORBIDDEN_WORKFLOW_REFERENCES), (
            f"credential or live-test reference leaked into ordinary CI: {value}"
        )


def test_quality_job_runs_ruff_check_and_format_check_on_ubuntu() -> None:
    workflow = load_workflow()
    quality_job = job(workflow, "quality")
    assert quality_job["runs-on"] == "ubuntu-latest"
    commands = step_commands(quality_job)
    normalized = [re.sub(r"\s+", " ", command).strip() for command in commands]
    assert "ruff check ." in normalized, "quality job must run 'ruff check .'"
    assert "ruff format --check ." in normalized, "quality job must run 'ruff format --check .'"


def test_package_job_installs_dev_extras_and_builds_exactly_once() -> None:
    workflow = load_workflow()
    package_job = job(workflow, "package")
    assert package_job["runs-on"] == "ubuntu-latest"
    commands = step_commands(package_job)

    assert any(".[dev]" in command for command in commands), "package job must install .[dev]"

    normalized = [re.sub(r"\s+", " ", command).strip() for command in commands]
    assert normalized.count("python -m build") == 1, "package job must build exactly once"
    assert "rm -rf dist build" in normalized, "package job must remove stale dist/build"


def test_package_job_checks_twine_and_audits_expected_version() -> None:
    workflow = load_workflow()
    commands = step_commands(job(workflow, "package"))
    joined = "\n".join(commands)
    assert "python -m twine check dist/*" in joined
    assert "scripts/audit_distribution.py dist --expected-version 0.1.0" in joined


def test_package_commands_run_in_release_gate_order() -> None:
    workflow = load_workflow()
    package_job = job(workflow, "package")
    commands = [re.sub(r"\s+", " ", command).strip() for command in step_commands(package_job)]
    required = [
        "rm -rf dist build",
        "python -m build",
        "python -m twine check dist/*",
        "python scripts/audit_distribution.py dist --expected-version 0.1.0",
        (
            "python scripts/verify_artifact_install.py "
            "dist/inferencefit-0.1.0-py3-none-any.whl 0.1.0 ."
        ),
        ("python scripts/verify_artifact_install.py dist/inferencefit-0.1.0.tar.gz 0.1.0 ."),
    ]
    assert all(command in commands for command in required)
    assert [commands.index(command) for command in required] == sorted(
        commands.index(command) for command in required
    )

    upload_index = next(
        index
        for index, step in enumerate(package_job["steps"])
        if str(step.get("uses", "")).startswith("actions/upload-artifact@")
    )
    sdist_index = next(
        index
        for index, step in enumerate(package_job["steps"])
        if "inferencefit-0.1.0.tar.gz" in step.get("run", "")
    )
    assert upload_index > sdist_index


def test_package_job_verifies_wheel_and_sdist_with_positional_interface() -> None:
    workflow = load_workflow()
    commands = step_commands(job(workflow, "package"))
    verifications = [
        command for command in commands if "scripts/verify_artifact_install.py" in command
    ]
    assert len(verifications) == 2, "package job must verify both artifacts"

    wheel = [command for command in verifications if ".whl" in command]
    sdist = [command for command in verifications if ".tar.gz" in command]
    assert len(wheel) == 1 and len(sdist) == 1

    for command in verifications:
        normalized = re.sub(r"\s+", " ", command).strip()
        assert normalized.endswith("0.1.0 ."), (
            "verifier must receive the positional '<artifact> 0.1.0 .' interface"
        )


def test_package_job_uploads_checked_distributions_as_immutable_artifact() -> None:
    workflow = load_workflow()
    package_job = job(workflow, "package")
    uploads = [
        step
        for step in package_job.get("steps", [])
        if isinstance(step, dict)
        and str(step.get("uses", "")).startswith("actions/upload-artifact@")
    ]
    assert len(uploads) == 1, "package job must upload the checked distributions once"
    upload = uploads[0]
    assert upload["uses"] == "actions/upload-artifact@v7"
    assert upload["with"]["name"] == "python-distributions"
    assert upload["with"]["path"] == "dist/*"
    assert upload["with"]["if-no-files-found"] == "error"


def test_workflows_use_current_official_action_majors() -> None:
    workflow = load_workflow()
    references = action_references(workflow)
    for action, major in CURRENT_ACTION_MAJORS.items():
        pinned = [reference for reference in references if reference.startswith(f"{action}@")]
        assert pinned, f"workflow must use {action}"
        assert all(reference == f"{action}@{major}" for reference in pinned), (
            f"{action} must be pinned to {major}"
        )
