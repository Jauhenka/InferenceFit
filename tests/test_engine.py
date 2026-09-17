from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import pytest

from inferencefit.contracts import TestCase, ValidatorSpec
from inferencefit.credentials import EnvironmentCredentialResolver
from inferencefit.metrics import aggregate_candidate, nearest_rank
from inferencefit.optimization import apply_constraints, pareto_frontier, rank_summaries
from inferencefit.validators import evaluate_validators


def case(expected=None):
    return TestCase.model_validate(
        {
            "id": "case-1",
            "request": {"messages": [{"role": "user", "content": "classify"}]},
            "expected": expected,
        }
    )


def test_validators_distinguish_runtime_and_eval_results():
    specs = [
        ValidatorSpec(
            id="schema",
            type="json_schema",
            routing_gate=True,
            config={"schema": {"type": "object", "required": ["category"]}},
        ),
        ValidatorSpec(id="exact", type="exact", target="/category", reference="/category"),
    ]
    result = evaluate_validators(specs, case({"category": "billing"}), '{"category":"billing"}')
    assert result.passed is True
    assert [item.runtime_capable for item in result.results] == [True, False]


def test_validation_failure_is_data_not_exception():
    specs = [ValidatorSpec(id="schema", type="json_schema", config={"schema": {"type": "object"}})]
    result = evaluate_validators(specs, case({}), "not json")
    assert result.passed is False
    assert result.results[0].passed is False


def test_credential_precedence_and_secret_safe_error(monkeypatch):
    monkeypatch.setenv("INFERENCEFIT_CREDENTIAL_FIREWORKS_MAIN", "explicit-secret")
    monkeypatch.setenv("FIREWORKS_API_KEY", "fallback-secret")
    resolver = EnvironmentCredentialResolver()
    assert resolver.resolve("fireworks-main", "fireworks") == "explicit-secret"
    monkeypatch.delenv("INFERENCEFIT_CREDENTIAL_FIREWORKS_MAIN")
    assert resolver.resolve("fireworks-main", "fireworks") == "fallback-secret"
    monkeypatch.delenv("FIREWORKS_API_KEY")
    with pytest.raises(Exception) as caught:
        resolver.resolve("fireworks-main", "fireworks")
    assert "secret" not in str(caught.value).lower()


def test_percentile_and_deterministic_ranking():
    assert nearest_rank([1, 2, 3, 4], 0.95) == 4
    summaries = [
        aggregate_candidate("b", []),
        aggregate_candidate("a", []),
    ]
    for summary in summaries:
        summary.eligible = True
        summary.validation_pass_rate = 1
        summary.provider_success_rate = 1
        summary.end_to_end_success_rate = 1
        summary.cost_per_1k_requests_usd = 1
        summary.p95_latency_ms = 10
    assert rank_summaries(summaries, "min_cost")[0].id == "a"


def test_constraints_and_pareto_keep_structured_reasons():
    good = aggregate_candidate("good", [])
    bad = aggregate_candidate("bad", [])
    for item in [good, bad]:
        item.provider_success_rate = 1
        item.provider_error_rate = 0
        item.validation_pass_rate = 1
        item.p95_latency_ms = 10
        item.cost_per_1k_requests_usd = 1
    good.end_to_end_success_rate = 1
    bad.end_to_end_success_rate = 0.5
    apply_constraints([good, bad], {"min_success_rate": 0.9})
    assert good.eligible is True
    assert bad.eligible is False
    assert bad.failed_constraints[0].metric == "min_success_rate"
    assert pareto_frontier([good, bad]) == ["good"]


@pytest.mark.asyncio
async def test_offline_benchmark_writes_complete_artifacts(tmp_path):
    from inferencefit import benchmark

    example = tmp_path / "example"
    example.mkdir()
    (example / "dataset.jsonl").write_text(
        json.dumps(
            {
                "id": "c1",
                "request": {"messages": [{"role": "user", "content": "x"}]},
                "expected": {"category": "a"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (example / "fixture.jsonl").write_text(
        json.dumps(
            {
                "case_id": "c1",
                "raw_output": json.dumps({"category": "a"}),
                "latency_ms": 5,
                "input_tokens": 10,
                "output_tokens": 2,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (example / "eval.yaml").write_text(
        """schema_version: '0.1'
dataset: {path: dataset.jsonl}
candidates:
  - id: fixture
    provider: fixture
    model: local
    parameters: {fixture_path: fixture.jsonl}
    pricing: {input_per_million: 1, output_per_million: 2}
validators:
  - {id: correct, type: exact, target: /category, reference: /category}
constraints: {min_success_rate: 1.0}
optimization: {objective: min_cost}
""",
        encoding="utf-8",
    )
    result = await benchmark(example / "eval.yaml", output_root=tmp_path / "runs")
    assert result.recommendation == "fixture"
    run_dir = tmp_path / "runs" / result.run_id
    assert {p.name for p in run_dir.iterdir()} >= {
        "manifest.json",
        "spec.yaml",
        "dataset.jsonl",
        "observations.jsonl",
        "result.json",
        "summary.md",
        "routing-policy.yaml",
    }
    assert "credential" not in (run_dir / "result.json").read_text(encoding="utf-8").lower()

    before = (run_dir / "observations.jsonl").read_text(encoding="utf-8")
    resumed = await benchmark(
        example / "eval.yaml", resume=result.run_id, output_root=tmp_path / "runs"
    )
    after = (run_dir / "observations.jsonl").read_text(encoding="utf-8")
    assert resumed.recommendation == "fixture"
    assert after == before


def test_eval_only_failure_does_not_trigger_cascade():
    from inferencefit.contracts import Observation, TokenUsage, ValidationResult, ValidationSummary
    from inferencefit.optimization import simulate_cascade

    primary = Observation(
        case_id="c",
        candidate_id="cheap",
        repetition=0,
        provider_status="success",
        raw_output='{"category":"wrong"}',
        usage=TokenUsage(input_tokens=1, output_tokens=1),
        latency_ms=1,
        cost_usd=0.1,
        validation=ValidationSummary(
            passed=False,
            results=[
                ValidationResult(validator_id="gate", passed=True, runtime_capable=True),
                ValidationResult(validator_id="exact", passed=False, runtime_capable=False),
            ],
        ),
    )
    fallback = primary.model_copy(
        update={
            "candidate_id": "strong",
            "cost_usd": 1.0,
            "validation": ValidationSummary(passed=True, results=[]),
        }
    )
    validators = [
        ValidatorSpec(id="gate", type="json_schema", routing_gate=True, config={"schema": {}}),
        ValidatorSpec(id="exact", type="exact"),
    ]
    summary = simulate_cascade("cheap", "strong", [primary, fallback], validators)
    assert summary.fallback_rate == 0
    assert summary.end_to_end_success_rate == 0

    primary.validation.results[0].passed = False
    summary = simulate_cascade("cheap", "strong", [primary, fallback], validators)
    assert summary.fallback_rate == 1
    assert summary.end_to_end_success_rate == 1


def test_daemon_endpoints_use_shared_core(tmp_path):
    from fastapi.testclient import TestClient

    from inferencefit.api import app, jobs

    jobs.clear()
    with TestClient(app) as client:
        assert client.get("/health").json()["status"] == "ok"
        response = client.post(
            "/v1/runs",
            json={
                "spec_path": str((Path("examples/basic/eval.yaml")).resolve()),
                "output_root": str(tmp_path / "api-runs"),
            },
        )
        assert response.status_code == 202
        run_id = response.json()["run_id"]
        state = None
        for _ in range(100):
            state = client.get(f"/v1/runs/{run_id}").json()["state"]
            if state in {"completed", "failed", "cancelled"}:
                break
            time.sleep(0.01)
        assert state == "completed"
        status = client.get(f"/v1/runs/{run_id}").json()
        assert status["completed_count"] == 6
        assert status["planned_count"] == 6
        result = client.get(f"/v1/runs/{run_id}/result")
        assert result.status_code == 200
        assert result.json()["recommendation"] == "cascade:cheap->strong"
        assert result.json()["run_id"] == run_id


def test_run_id_rejects_path_traversal(tmp_path):
    from inferencefit.storage import FilesystemArtifactStore

    store = FilesystemArtifactStore(tmp_path)
    with pytest.raises(ValueError, match="run_id"):
        store.run_dir("../outside")


def test_cascade_preserves_unknown_latency():
    from inferencefit.contracts import Observation, ValidationSummary
    from inferencefit.optimization import simulate_cascade

    observation = Observation(
        case_id="c",
        candidate_id="cheap",
        repetition=0,
        provider_status="success",
        raw_output="ok",
        latency_ms=None,
        cost_usd=0.1,
        validation=ValidationSummary(passed=True, results=[]),
    )
    summary = simulate_cascade("cheap", "strong", [observation], [])
    assert summary.p95_latency_ms is None


@pytest.mark.asyncio
async def test_internal_worker_error_marks_manifest_failed_without_deadlock(tmp_path):
    from inferencefit import benchmark

    root = tmp_path / "broken"
    root.mkdir()
    (root / "dataset.jsonl").write_text(
        json.dumps(
            {
                "id": "c",
                "request": {"messages": [{"role": "user", "content": "x"}]},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "fixture.jsonl").write_text(
        json.dumps({"case_id": "c", "latency_ms": 1}) + "\n", encoding="utf-8"
    )
    (root / "eval.yaml").write_text(
        """schema_version: '0.1'
dataset: {path: dataset.jsonl}
candidates:
  - {id: broken, provider: fixture, model: local, parameters: {fixture_path: fixture.jsonl}}
""",
        encoding="utf-8",
    )
    with pytest.raises(ExceptionGroup):
        await asyncio.wait_for(
            benchmark(root / "eval.yaml", output_root=tmp_path / "runs", run_id="broken-run"),
            timeout=2,
        )
    manifest = json.loads(
        (tmp_path / "runs" / "broken-run" / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["status"] == "failed"


@pytest.mark.asyncio
async def test_cancellation_stops_workers_before_return(tmp_path):
    from inferencefit.contracts import EvaluationSpec
    from inferencefit.execution import run_evaluations
    from inferencefit.providers import ProviderResponse
    from inferencefit.storage import FilesystemArtifactStore

    spec = EvaluationSpec.model_validate(
        {
            "dataset": {"path": "unused"},
            "candidates": [{"id": "slow", "provider": "fixture", "model": "slow"}],
        }
    )

    class SlowProvider:
        async def complete(self, candidate, test_case, repetition):
            await asyncio.sleep(10)
            return ProviderResponse(raw_output="ok", latency_ms=1)

    store = FilesystemArtifactStore(tmp_path / "runs")
    store.create("cancel-run")
    task = asyncio.create_task(
        run_evaluations(spec, [case()], lambda candidate: SlowProvider(), store, "cancel-run")
    )
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert store.observations("cancel-run") == []
