import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import installed_distribution_smoke as smoke  # noqa: E402
import verify_artifact_install as verifier  # noqa: E402


def test_assert_import_is_outside_source_tree_rejects_editable_import(tmp_path):
    source_root = tmp_path / "repo"
    package_file = source_root / "src" / "inferencefit" / "__init__.py"
    package_file.parent.mkdir(parents=True)
    package_file.touch()

    with pytest.raises(RuntimeError, match="source tree"):
        smoke.assert_import_is_outside_source_tree(package_file, source_root)


def test_assert_import_is_outside_source_tree_rejects_source_root_itself(tmp_path):
    with pytest.raises(RuntimeError, match="source tree"):
        smoke.assert_import_is_outside_source_tree(tmp_path, tmp_path)


@pytest.mark.parametrize(
    ("os_name", "relative"),
    [("nt", Path("Scripts/python.exe")), ("posix", Path("bin/python"))],
)
def test_venv_python_path_is_cross_platform(tmp_path, os_name, relative):
    assert verifier.venv_python_path(tmp_path, os_name) == tmp_path / relative


@pytest.mark.parametrize(
    ("os_name", "relative"),
    [("nt", Path("Scripts")), ("posix", Path("bin"))],
)
def test_venv_bin_path_is_cross_platform(tmp_path, os_name, relative):
    assert verifier.venv_bin_path(tmp_path, os_name) == tmp_path / relative


def test_write_fixture_workload_creates_two_case_relative_fixture_spec(tmp_path):
    spec_path = smoke.write_fixture_workload(tmp_path)

    dataset_path = tmp_path / "dataset.jsonl"
    fixture_path = tmp_path / "fixture.jsonl"
    dataset_cases = [line for line in dataset_path.read_text(encoding="utf-8").splitlines() if line]
    fixture_cases = [line for line in fixture_path.read_text(encoding="utf-8").splitlines() if line]
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))

    assert spec_path == tmp_path / "eval.yaml"
    assert len(dataset_cases) == 2
    assert len(fixture_cases) == 2
    assert [yaml.safe_load(case)["id"] for case in dataset_cases] == ["alpha", "beta"]
    assert [yaml.safe_load(case)["case_id"] for case in fixture_cases] == ["alpha", "beta"]
    assert spec["dataset"]["path"] == "dataset.jsonl"
    assert spec["candidates"] == [
        {
            "id": "fixture",
            "provider": "fixture",
            "model": "local",
            "parameters": {"fixture_path": "fixture.jsonl"},
            "pricing": {"input_per_million": 1, "output_per_million": 1},
        }
    ]
    assert spec["validators"] == [
        {
            "id": "schema",
            "type": "json_schema",
            "config": {
                "schema": {
                    "type": "object",
                    "required": ["category"],
                    "properties": {"category": {"type": "string"}},
                }
            },
        },
        {"id": "exact", "type": "exact", "target": "/category", "reference": "/category"},
    ]
    assert spec["constraints"] == {"min_success_rate": 1.0}
    assert spec["execution"]["repetitions"] == 1


def test_run_checked_includes_real_failing_subprocess_diagnostics(tmp_path):
    command = "import sys; print('stdout-text'); print('stderr-text', file=sys.stderr); sys.exit(7)"
    with pytest.raises(RuntimeError, match=r"stdout-text.*stderr-text") as caught:
        smoke.run_checked(
            [
                sys.executable,
                "-c",
                command,
            ],
            tmp_path,
        )

    assert "exit code 7" in str(caught.value)
    assert sys.executable in str(caught.value)


def test_verify_run_checked_includes_real_failing_subprocess_diagnostics(tmp_path):
    command = "import sys; print('verify-out'); print('verify-err', file=sys.stderr); sys.exit(3)"
    with pytest.raises(RuntimeError, match=r"verify-out.*verify-err"):
        verifier.run_checked(
            [
                sys.executable,
                "-c",
                command,
            ],
            tmp_path,
        )


def result_payload() -> dict:
    return {
        "schema_version": "0.1",
        "status": "completed",
        "candidate_summaries": [
            {
                "id": "fixture",
                "planned_count": 2,
                "provider_success_count": 2,
                "provider_error_count": 0,
            }
        ],
        "recommendation": "fixture",
    }


def test_assert_complete_fixture_result_accepts_expected_two_case_result(tmp_path):
    result = tmp_path / "result.json"
    result.write_text(json.dumps(result_payload()), encoding="utf-8")

    smoke.assert_complete_fixture_result(result)


def test_assert_complete_fixture_result_rejects_malformed_json(tmp_path):
    result = tmp_path / "result.json"
    result.write_text("{not-json", encoding="utf-8")

    with pytest.raises(RuntimeError, match="invalid result.json"):
        smoke.assert_complete_fixture_result(result)


@pytest.mark.parametrize(
    ("update", "message"),
    [
        ({"status": "failed"}, "completed"),
        ({"recommendation": None}, "recommendation"),
        ({"candidate_summaries": []}, "fixture"),
    ],
)
def test_assert_complete_fixture_result_rejects_incomplete_result(tmp_path, update, message):
    payload = result_payload()
    payload.update(update)
    result = tmp_path / "result.json"
    result.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(RuntimeError, match=message):
        smoke.assert_complete_fixture_result(result)


def test_smoke_main_rejects_source_tree_import_before_running_child(tmp_path, monkeypatch):
    package_file = tmp_path / "repo" / "src" / "inferencefit" / "__init__.py"
    package_file.parent.mkdir(parents=True)
    package_file.touch()
    monkeypatch.setitem(
        sys.modules, "inferencefit", SimpleNamespace(__version__="0.1.0", __file__=package_file)
    )
    monkeypatch.setattr(smoke.shutil, "which", lambda _name: pytest.fail("child should not run"))

    with pytest.raises(RuntimeError, match="source tree"):
        smoke.main("0.1.0", tmp_path / "repo")


def test_smoke_main_rejects_host_console_script_from_retained_path(tmp_path, monkeypatch):
    package_file = tmp_path / "site-packages" / "inferencefit" / "__init__.py"
    package_file.parent.mkdir(parents=True)
    package_file.touch()
    isolated_python = (
        tmp_path / "isolated" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    )
    isolated_python.parent.mkdir(parents=True)
    isolated_python.touch()
    host_bin = tmp_path / "host-bin"
    host_bin.mkdir()
    host_script = host_bin / ("inferencefit.exe" if os.name == "nt" else "inferencefit")
    host_script.touch()
    host_script.chmod(0o755)

    monkeypatch.setitem(
        sys.modules, "inferencefit", SimpleNamespace(__version__="0.1.0", __file__=package_file)
    )
    monkeypatch.setattr(sys, "executable", str(isolated_python))
    monkeypatch.setenv("PATH", str(host_bin))
    monkeypatch.setattr(
        smoke,
        "run_checked",
        lambda *_args, **_kwargs: pytest.fail("host console script must not run"),
    )

    with pytest.raises(RuntimeError, match="adjacent to the isolated interpreter"):
        smoke.main("0.1.0", None)


@pytest.mark.parametrize(
    ("os_name", "python_relative", "script_name"),
    [
        ("nt", Path("Scripts/python.exe"), "inferencefit.exe"),
        ("posix", Path("bin/python"), "inferencefit"),
    ],
)
def test_console_script_path_is_adjacent_to_python(tmp_path, os_name, python_relative, script_name):
    python_executable = tmp_path / python_relative

    assert smoke.console_script_path(python_executable, os_name) == (
        python_executable.parent / script_name
    )


def test_verify_main_uses_isolated_venv_and_prefixed_child_path(tmp_path, monkeypatch):
    artifact = tmp_path / "artifact.whl"
    artifact.touch()
    source_root = tmp_path / "source"
    source_root.mkdir()
    calls = []

    class FakeBuilder:
        def __init__(self, **kwargs):
            assert kwargs == {"with_pip": True, "system_site_packages": False}

        def create(self, environment):
            environment.mkdir()
            verifier.venv_bin_path(environment).mkdir()

    def fake_run(command, **kwargs):
        if len(command) == 4:
            assert Path(command[1]).is_file()
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(verifier.venv, "EnvBuilder", FakeBuilder)
    monkeypatch.setattr(verifier.subprocess, "run", fake_run)
    monkeypatch.setenv("PYTHONPATH", "should-be-removed")
    monkeypatch.setenv("PATH", "host-bin" + os.pathsep + "other-bin")

    assert verifier.main(artifact, "0.1.0", source_root) == 0

    assert len(calls) == 2
    child_command, child_options = calls[1]
    environment = Path(child_command[0]).parents[1]
    assert child_options["cwd"] == Path(child_command[1]).parent
    assert "PYTHONPATH" not in child_options["env"]
    assert child_options["env"]["PATH"].split(os.pathsep)[0] == str(
        verifier.venv_bin_path(environment)
    )
