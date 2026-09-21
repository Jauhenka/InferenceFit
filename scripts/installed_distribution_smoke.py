"""Smoke-test an installed InferenceFit distribution outside its source tree."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path


def assert_import_is_outside_source_tree(package_file: Path, source_root: Path | None) -> None:
    """Reject imports that resolve into the checkout being verified."""
    if source_root is None:
        return
    try:
        package_file.resolve().relative_to(source_root.resolve())
    except ValueError:
        return
    raise RuntimeError(f"inferencefit imported from source tree: {package_file}")


def write_fixture_workload(directory: Path) -> Path:
    """Write a deterministic two-case offline workload and return its spec path."""
    cases = [("alpha", "first", "alpha"), ("beta", "second", "beta")]
    dataset = [
        {
            "id": case_id,
            "request": {"messages": [{"role": "user", "content": prompt}]},
            "expected": {"category": category},
        }
        for case_id, prompt, category in cases
    ]
    responses = [
        {
            "case_id": case_id,
            "repetition": 0,
            "raw_output": json.dumps({"category": category}),
            "latency_ms": 1,
            "input_tokens": 1,
            "output_tokens": 1,
        }
        for case_id, _prompt, category in cases
    ]
    (directory / "dataset.jsonl").write_text(
        "".join(json.dumps(record) + "\n" for record in dataset), encoding="utf-8"
    )
    (directory / "fixture.jsonl").write_text(
        "".join(json.dumps(record) + "\n" for record in responses), encoding="utf-8"
    )
    spec = {
        "schema_version": "0.1",
        "dataset": {"path": "dataset.jsonl"},
        "candidates": [
            {
                "id": "fixture",
                "provider": "fixture",
                "model": "local",
                "parameters": {"fixture_path": "fixture.jsonl"},
            }
        ],
        "validators": [
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
        ],
        "constraints": {"min_success_rate": 1.0},
        "execution": {"repetitions": 1},
    }
    spec_path = directory / "eval.yaml"
    import yaml

    spec_path.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")
    return spec_path


def run_checked(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a command and retain its decoded output for contract checks."""
    return subprocess.run(command, cwd=cwd, check=True, text=True, capture_output=True)


def main(expected_version: str, source_root: Path | None) -> int:
    import inferencefit

    if inferencefit.__version__ != expected_version:
        raise RuntimeError(
            f"expected inferencefit {expected_version}, found {inferencefit.__version__}"
        )
    assert_import_is_outside_source_tree(Path(inferencefit.__file__), source_root)

    executable = shutil.which("inferencefit")
    if executable is None:
        raise RuntimeError("inferencefit console script was not found")

    with tempfile.TemporaryDirectory(prefix="inferencefit-smoke-") as temporary:
        workdir = Path(temporary)
        spec_path = write_fixture_workload(workdir)
        help_result = run_checked([executable, "--help"], workdir)
        validation_result = run_checked([executable, "validate", str(spec_path)], workdir)
        benchmark_result = run_checked([executable, "benchmark", str(spec_path)], workdir)

        if "Workload-specific LLM benchmarking" not in help_result.stdout:
            raise RuntimeError("console help did not identify InferenceFit")
        if "Valid EvaluationSpec 0.1" not in validation_result.stdout:
            raise RuntimeError("evaluation spec validation did not succeed")
        if "Provider successes/failures: 2/0" not in benchmark_result.stdout:
            raise RuntimeError("benchmark did not report two provider successes and zero failures")
        results = list((workdir / ".inferencefit" / "runs").glob("*/result.json"))
        if len(results) != 1:
            raise RuntimeError(f"expected exactly one complete result.json, found {len(results)}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("expected_version")
    parser.add_argument("source_root", nargs="?")
    arguments = parser.parse_args()
    source_root = Path(arguments.source_root) if arguments.source_root else None
    raise SystemExit(main(arguments.expected_version, source_root))
