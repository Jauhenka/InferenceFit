import sys
from pathlib import Path

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


@pytest.mark.parametrize(
    ("os_name", "relative"),
    [("nt", Path("Scripts/python.exe")), ("posix", Path("bin/python"))],
)
def test_venv_python_path_is_cross_platform(tmp_path, os_name, relative):
    assert verifier.venv_python_path(tmp_path, os_name) == tmp_path / relative


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
