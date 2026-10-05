"""Smoke-test an installed InferenceFit distribution outside its source tree."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def assert_import_is_outside_source_tree(package_file: Path, source_root: Path | None) -> None:
    """Reject imports that resolve into the checkout being verified."""
    if source_root is None:
        return
    current = package_file.resolve()
    source = source_root.resolve()
    while True:
        if current.samefile(source):
            raise RuntimeError(f"inferencefit imported from source tree: {package_file}")
        if current.parent == current:
            return
        current = current.parent


def console_script_path(python_executable: Path, os_name: str) -> Path:
    """Return the platform-specific console script beside a Python executable."""
    script_name = "inferencefit.exe" if os_name == "nt" else "inferencefit"
    return python_executable.parent / script_name


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
                "pricing": {"input_per_million": 1, "output_per_million": 1},
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


def write_custom_workload(directory: Path, base_url: str) -> Path:
    """Write one credentialless generic-provider case for the installed CLI."""
    import yaml

    case = {
        "id": "custom-case",
        "request": {"messages": [{"role": "user", "content": "classify"}]},
        "expected": {"category": "a"},
    }
    (directory / "custom-dataset.jsonl").write_text(json.dumps(case) + "\n", encoding="utf-8")
    spec = {
        "schema_version": "0.1",
        "dataset": {"path": "custom-dataset.jsonl"},
        "candidates": [
            {
                "id": "custom",
                "provider": "custom",
                "model": "native/model",
                "base_url": base_url,
            }
        ],
        "validators": [
            {"id": "exact", "type": "exact", "target": "/category", "reference": "/category"}
        ],
        "constraints": {"min_success_rate": 1.0},
        "execution": {"retry": {"max_attempts": 1}},
    }
    spec_path = directory / "custom-eval.yaml"
    spec_path.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")
    return spec_path


def run_custom_smoke(executable: str, workdir: Path) -> tuple[dict, dict]:
    """Exercise the installed CLI against a real loopback chat-completions server."""
    requests: list[dict] = []

    class ChatHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            requests.append(
                {
                    "path": self.path,
                    "body": json.loads(body),
                    "authorization": self.headers.get("Authorization"),
                }
            )
            response = json.dumps(
                {
                    "model": "native/model",
                    "choices": [{"message": {"content": '{"category":"a"}'}}],
                }
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)

        def log_message(self, _format: str, *_args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), ChatHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        spec_path = write_custom_workload(workdir, f"http://127.0.0.1:{server.server_port}/v1")
        previous_results = set((workdir / ".inferencefit" / "runs").glob("*/result.json"))
        validation = run_checked([executable, "validate", str(spec_path)], workdir)
        if "Valid EvaluationSpec 0.1" not in validation.stdout:
            raise RuntimeError("custom evaluation spec validation did not succeed")
        benchmark = run_checked([executable, "benchmark", str(spec_path)], workdir)
        if "Provider successes/failures: 1/0" not in benchmark.stdout:
            raise RuntimeError("custom benchmark did not report one provider success")

        current_results = set((workdir / ".inferencefit" / "runs").glob("*/result.json"))
        new_results = current_results - previous_results
        if len(new_results) != 1:
            raise RuntimeError(f"expected one custom result.json, found {len(new_results)}")
        result_path = new_results.pop()
        result = json.loads(result_path.read_text(encoding="utf-8"))
        summaries = result.get("candidate_summaries")
        if (
            result.get("status") != "completed"
            or not isinstance(summaries, list)
            or len(summaries) != 1
            or summaries[0].get("id") != "custom"
            or summaries[0].get("provider_success_count") != 1
            or summaries[0].get("provider_error_count") != 0
            or summaries[0].get("total_cost_usd") is not None
        ):
            raise RuntimeError("custom result did not represent one successful unknown-cost case")
        observations = (
            (result_path.parent / "observations.jsonl").read_text(encoding="utf-8").splitlines()
        )
        if len(observations) != 1:
            raise RuntimeError("custom benchmark did not produce one observation")
        observation = json.loads(observations[0])
        if (
            observation.get("provider") != "custom"
            or observation.get("provider_status") != "success"
            or observation.get("cost_usd") is not None
            or observation.get("cost_source") is not None
        ):
            raise RuntimeError("custom observation did not preserve provider and unknown cost")
        if len(requests) != 1 or requests[0] != {
            "path": "/v1/chat/completions",
            "body": {
                "model": "native/model",
                "messages": [{"role": "user", "content": "classify"}],
            },
            "authorization": None,
        }:
            raise RuntimeError(
                "custom endpoint did not receive the expected credentialless request"
            )
        return requests[0], observation
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def run_checked(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a command and retain its decoded output for contract checks."""
    try:
        return subprocess.run(command, cwd=cwd, check=True, text=True, capture_output=True)
    except subprocess.CalledProcessError as error:
        raise RuntimeError(
            f"command failed with exit code {error.returncode}: {shlex.join(command)}; "
            f"stdout={error.stdout!r}; stderr={error.stderr!r}"
        ) from error


def assert_complete_fixture_result(
    result_path: Path, expected_candidate_id: str = "fixture"
) -> None:
    """Confirm the one result artifact is the expected two-case fixture run."""
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"invalid result.json: {result_path}: {error}") from error
    if result.get("schema_version") != "0.1" or result.get("status") != "completed":
        raise RuntimeError("result.json is not a completed EvaluationSpec 0.1 result")
    summaries = result.get("candidate_summaries")
    if not isinstance(summaries, list) or len(summaries) != 1:
        raise RuntimeError("result.json does not contain one fixture candidate summary")
    summary = summaries[0]
    if (
        summary.get("id") != expected_candidate_id
        or summary.get("planned_count") != 2
        or summary.get("provider_success_count") != 2
        or summary.get("provider_error_count") != 0
    ):
        raise RuntimeError("result.json does not represent two successful fixture cases")
    if result.get("recommendation") != expected_candidate_id:
        raise RuntimeError(f"result.json recommendation is not {expected_candidate_id}")


def assert_packaged_skill_path(output: str, package_root: Path) -> None:
    """Confirm `skill path` points at a complete installed package resource."""

    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if len(lines) != 1:
        raise RuntimeError(f"skill path did not print exactly one directory: {lines!r}")
    skill_root = Path(lines[0]).resolve()
    installed_root = package_root.resolve()
    if not skill_root.is_relative_to(installed_root):
        raise RuntimeError(f"skill path is outside the installed package: {skill_root}")
    required = [
        skill_root / "SKILL.md",
        skill_root / "references" / "presets.md",
        skill_root / "references" / "validators.md",
        skill_root / "references" / "interpreting-results.md",
    ]
    for path in required:
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as error:
            raise RuntimeError(f"packaged skill resource is unreadable: {path}: {error}") from error
        if not content.strip():
            raise RuntimeError(f"packaged skill resource is empty: {path}")


def assert_named_decentralized_profiles() -> dict[str, str]:
    """Confirm installed registry dispatches each new name through the shared adapter."""
    from inferencefit.contracts import CandidateSpec
    from inferencefit.providers import OpenAICompatibleProvider, create_provider

    class NoCredentialResolver:
        def resolve(self, _reference: str | None, _provider: str) -> None:
            return None

    expected = {
        "chutes": "https://llm.chutes.ai/v1",
        "morpheus": "https://api.mor.org/api/v1",
        "nosana": "https://inference.nosana.com/v1",
    }
    actual = {}
    for provider, base_url in expected.items():
        candidate = CandidateSpec(id=provider, provider=provider, model="native/model")
        adapter = create_provider(candidate, spec_dir=Path.cwd(), resolver=NoCredentialResolver())
        if type(adapter) is not OpenAICompatibleProvider:
            raise RuntimeError(f"{provider} did not select the shared chat adapter")
        actual[provider] = adapter._base_url(candidate)
        if actual[provider] != base_url:
            raise RuntimeError(f"{provider} did not resolve its expected API base")
    return actual


def main(expected_version: str, source_root: Path | None) -> int:
    import inferencefit

    if inferencefit.__version__ != expected_version:
        raise RuntimeError(
            f"expected inferencefit {expected_version}, found {inferencefit.__version__}"
        )
    assert_import_is_outside_source_tree(Path(inferencefit.__file__), source_root)

    expected_executable = console_script_path(Path(sys.executable), os.name)
    discovered_executable = shutil.which("inferencefit")
    if (
        discovered_executable is None
        or Path(discovered_executable).resolve() != expected_executable.resolve()
    ):
        raise RuntimeError(
            "inferencefit console script is not adjacent to the isolated interpreter: "
            f"expected {expected_executable}; PATH resolved to {discovered_executable!r}"
        )
    executable = str(expected_executable)

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
        assert_complete_fixture_result(results[0])

        presets_result = run_checked([executable, "presets"], workdir)
        for preset_id in ("coding", "document-processing", "structured-extraction"):
            if f"{preset_id}:" not in presets_result.stdout:
                raise RuntimeError(f"preset listing is missing {preset_id}")

        preset_dir = workdir / "structured-extraction"
        run_checked(
            [executable, "init", "--preset", "structured-extraction", str(preset_dir)],
            workdir,
        )
        preset_spec = preset_dir / "eval.yaml"
        preset_validation = run_checked([executable, "validate", str(preset_spec)], workdir)
        if "Valid EvaluationSpec 0.1" not in preset_validation.stdout:
            raise RuntimeError("generated preset validation did not succeed")
        previous_results = set(results)
        preset_benchmark = run_checked([executable, "benchmark", str(preset_spec)], workdir)
        if "Provider successes/failures: 2/0" not in preset_benchmark.stdout:
            raise RuntimeError("generated preset benchmark did not report two successes")
        current_results = set((workdir / ".inferencefit" / "runs").glob("*/result.json"))
        generated_results = current_results - previous_results
        if len(generated_results) != 1:
            raise RuntimeError(
                f"expected one generated-preset result.json, found {len(generated_results)}"
            )
        assert_complete_fixture_result(
            generated_results.pop(), expected_candidate_id="offline-fixture"
        )

        skill_result = run_checked([executable, "skill", "path"], workdir)
        assert_packaged_skill_path(skill_result.stdout, Path(inferencefit.__file__).parent)
        assert_named_decentralized_profiles()
        run_custom_smoke(executable, workdir)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("expected_version")
    parser.add_argument("source_root", nargs="?")
    arguments = parser.parse_args()
    source_root = Path(arguments.source_root) if arguments.source_root else None
    raise SystemExit(main(arguments.expected_version, source_root))
