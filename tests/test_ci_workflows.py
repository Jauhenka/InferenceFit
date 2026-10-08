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
RELEASE_WORKFLOW_PATH = ROOT / ".github" / "workflows" / "release.yml"
TESTPYPI_WORKFLOW_PATH = ROOT / ".github" / "workflows" / "testpypi.yml"

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

CURRENT_PUBLISH_ACTION_MAJORS = {
    **CURRENT_ACTION_MAJORS,
    "actions/download-artifact": "v8",
}
PYPA_PUBLISH_ACTION = "pypa/gh-action-pypi-publish@release/v1"

FORBIDDEN_WORKFLOW_REFERENCES = (
    "secrets.",
    "inferencefit_live_tests",
    "api_key",
    "apikey",
    "credential",
    "password",
)


def load_workflow(path: Path = WORKFLOW_PATH) -> dict[str, Any]:
    assert path.is_file(), f"missing workflow: {path}"
    loaded = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
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
    assert "scripts/audit_distribution.py dist --expected-version 0.2.4" in joined


def test_package_commands_run_in_release_gate_order() -> None:
    workflow = load_workflow()
    package_job = job(workflow, "package")
    commands = [re.sub(r"\s+", " ", command).strip() for command in step_commands(package_job)]
    required = [
        "rm -rf dist build",
        "python -m build",
        "python -m twine check dist/*",
        "python scripts/audit_distribution.py dist --expected-version 0.2.4",
        (
            "python scripts/verify_artifact_install.py "
            "dist/inferencefit-0.2.4-py3-none-any.whl 0.2.4 ."
        ),
        ("python scripts/verify_artifact_install.py dist/inferencefit-0.2.4.tar.gz 0.2.4 ."),
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
        if "inferencefit-0.2.4.tar.gz" in step.get("run", "")
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
        assert normalized.endswith("0.2.4 ."), (
            "verifier must receive the positional '<artifact> 0.2.4 .' interface"
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


def publishing_workflows() -> Iterator[tuple[Path, dict[str, Any]]]:
    for path in (RELEASE_WORKFLOW_PATH, TESTPYPI_WORKFLOW_PATH):
        yield path, load_workflow(path)


def test_release_workflow_triggers_only_for_version_tags() -> None:
    workflow = load_workflow(RELEASE_WORKFLOW_PATH)
    assert workflow["on"] == {"push": {"tags": ["v*"]}}


def test_testpypi_workflow_is_manual_only() -> None:
    workflow = load_workflow(TESTPYPI_WORKFLOW_PATH)
    assert workflow["on"] == {"workflow_dispatch": ""}


def test_publishing_workflows_separate_build_from_publish() -> None:
    for path, workflow in publishing_workflows():
        assert set(workflow["jobs"]) == {"build", "publish"}, path
        assert workflow["permissions"] == {}, path
        build = job(workflow, "build")
        publish = job(workflow, "publish")
        assert build["permissions"] == {"contents": "read"}, path
        assert publish["needs"] == "build", path
        assert publish["permissions"] == {"id-token": "write"}, path


def test_release_build_derives_and_confirms_tag_version() -> None:
    workflow = load_workflow(RELEASE_WORKFLOW_PATH)
    commands = step_commands(job(workflow, "build"))
    joined = "\n".join(commands)
    assert "GITHUB_REF_NAME#v" in joined
    assert "RELEASE_VERSION" in joined
    assert "inferencefit.__version__" in joined
    assert "['project']['version']" not in joined
    assert not {"0.2.0", "0.2.1", "0.2.2", "0.2.3"}.intersection(joined.split()), (
        "tag release build must not hard-code the package version"
    )
    assert 'audit_distribution.py dist --expected-version "$RELEASE_VERSION"' in joined
    assert joined.count('"$RELEASE_VERSION" .') == 2


def test_testpypi_build_confirms_fixed_release_candidate_version() -> None:
    workflow = load_workflow(TESTPYPI_WORKFLOW_PATH)
    joined = "\n".join(step_commands(job(workflow, "build")))
    assert "RELEASE_VERSION=0.2.4" in joined
    assert "inferencefit.__version__" in joined
    assert "['project']['version']" not in joined


def test_publishing_builds_run_all_release_gates_in_order() -> None:
    for path, workflow in publishing_workflows():
        build = job(workflow, "build")
        commands = [re.sub(r"\s+", " ", command).strip() for command in step_commands(build)]
        joined = "\n".join(commands)
        build_commands = [command for command in commands if command == "python -m build"]
        assert build_commands == ["python -m build"], path

        required_fragments = [
            "rm -rf dist build",
            "python -m build",
            "python -m twine check dist/*",
            "scripts/audit_distribution.py dist --expected-version",
            "scripts/verify_artifact_install.py",
        ]
        indices = [
            next(index for index, command in enumerate(commands) if fragment in command)
            for fragment in required_fragments
        ]
        assert indices == sorted(indices), path
        assert joined.count("scripts/verify_artifact_install.py") == 2, path
        assert ".whl" in joined and ".tar.gz" in joined, path
        assert "--artifact" not in joined and "--source-root" not in joined, path

        upload_steps = [
            step
            for step in build["steps"]
            if str(step.get("uses", "")).startswith("actions/upload-artifact@")
        ]
        assert len(upload_steps) == 1, path
        upload = upload_steps[0]
        assert upload["with"] == {
            "name": "python-distributions",
            "path": "dist/*",
            "if-no-files-found": "error",
        }, path
        assert build["steps"].index(upload) > max(
            index
            for index, step in enumerate(build["steps"])
            if "scripts/verify_artifact_install.py" in step.get("run", "")
        ), path


def test_publishing_jobs_only_download_and_publish_verified_artifact() -> None:
    forbidden_actions = ("actions/checkout@", "actions/setup-python@", "actions/upload-artifact@")
    forbidden_commands = ("pip install", "python -m build", "audit_distribution", "verify_artifact")
    expected_environments = {
        RELEASE_WORKFLOW_PATH: "pypi",
        TESTPYPI_WORKFLOW_PATH: "testpypi",
    }

    for path, workflow in publishing_workflows():
        publish = job(workflow, "publish")
        assert publish["environment"] == expected_environments[path]
        assert len(publish["steps"]) == 2, path
        references = action_references(publish)
        assert references == ["actions/download-artifact@v8", PYPA_PUBLISH_ACTION], path
        assert not any(reference.startswith(forbidden_actions) for reference in references), path
        assert not any(
            fragment in command
            for command in step_commands(publish)
            for fragment in forbidden_commands
        ), path

        download = publish["steps"][0]
        assert download["with"] == {"name": "python-distributions", "path": "dist"}, path


def test_testpypi_publish_uses_test_repository_and_pypi_uses_default() -> None:
    release_publish = job(load_workflow(RELEASE_WORKFLOW_PATH), "publish")
    test_publish = job(load_workflow(TESTPYPI_WORKFLOW_PATH), "publish")
    release_action = release_publish["steps"][1]
    test_action = test_publish["steps"][1]
    assert release_action["uses"] == PYPA_PUBLISH_ACTION
    assert "with" not in release_action
    assert test_action["uses"] == PYPA_PUBLISH_ACTION
    assert test_action["with"] == {"repository-url": "https://test.pypi.org/legacy/"}


def test_publishing_workflows_use_current_official_actions() -> None:
    for path, workflow in publishing_workflows():
        references = action_references(workflow)
        for action, major in CURRENT_PUBLISH_ACTION_MAJORS.items():
            pinned = [reference for reference in references if reference.startswith(f"{action}@")]
            assert pinned, f"{path} must use {action}"
            assert all(reference == f"{action}@{major}" for reference in pinned), (
                f"{path}: {action} must be pinned to {major}"
            )
        assert references.count(PYPA_PUBLISH_ACTION) == 1, path


def test_publishing_workflows_do_not_reference_long_lived_credentials() -> None:
    forbidden = ("secrets.", "token", "password", "api_key", "apikey", "credential")
    for path, workflow in publishing_workflows():
        for value in strings(workflow):
            lowered = value.lower()
            if lowered == "id-token":
                continue
            assert not any(fragment in lowered for fragment in forbidden), (
                f"{path}: long-lived credential reference found: {value}"
            )
