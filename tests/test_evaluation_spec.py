"""Focused tests for EvaluationSpec contracts and the YAML/JSON loader."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from inferencefit.contracts.candidates import CandidateSpec
from inferencefit.contracts.dataset import TestCase
from inferencefit.contracts.evaluation import EvaluationSpec
from inferencefit.contracts.execution import ExecutionSpec, RetrySpec
from inferencefit.contracts.optimization import OptimizationSpec
from inferencefit.contracts.validators import ValidatorSpec
from inferencefit.errors import SpecLoadError
from inferencefit.spec import LoadedEvaluationSpec, load_evaluation_spec


def _minimal_document() -> dict:
    return {
        "schema_version": "0.1",
        "dataset": {"path": "cases.jsonl"},
        "candidates": [
            {
                "id": "cheap",
                "provider": "fireworks",
                "model": "llama-8b",
                "parameters": {"temperature": 0, "max_tokens": 32},
            },
            {
                "id": "strong",
                "provider": "openrouter",
                "model": "llama-70b",
                "parameters": {"temperature": 0},
            },
        ],
        "execution": {
            "concurrency": 2,
            "timeout_ms": 30000,
            "repetitions": 2,
            "retry": {"max_attempts": 3, "initial_backoff_ms": 250, "max_backoff_ms": 10000},
        },
        "validators": [
            {
                "id": "gate",
                "type": "enum",
                "config": {"values": ["yes", "no"]},
                "routing_gate": True,
            }
        ],
        "constraints": [
            {"id": "min-success", "metric": "min_success_rate", "threshold": 0.8},
        ],
        "optimization": {
            "objective": "min_cost",
            "cascade": {"primary": "cheap", "fallbacks": ["strong"]},
        },
    }


def test_loads_yaml_and_json_equivalently(tmp_path) -> None:
    yaml_path = tmp_path / "eval.yaml"
    yaml_path.write_text(
        "\n".join(
            [
                "schema_version: '0.1'",
                "dataset:",
                "  path: cases.jsonl",
                "candidates:",
                "  - id: cheap",
                "    provider: fireworks",
                "    model: llama-8b",
                "    parameters:",
                "      temperature: 0",
                "execution:",
                "  timeout_ms: 30000",
                "  retry:",
                "    initial_backoff_ms: 250",
                "    max_backoff_ms: 10000",
                "optimization:",
                "  objective: min_cost",
            ]
        ),
        encoding="utf-8",
    )
    json_path = tmp_path / "eval.json"
    json_path.write_text(json.dumps(_minimal_document()), encoding="utf-8")

    from_yaml = load_evaluation_spec(yaml_path)
    from_json = load_evaluation_spec(json_path)

    assert isinstance(from_yaml, LoadedEvaluationSpec)
    assert isinstance(from_yaml.spec, EvaluationSpec)
    assert from_yaml.spec.schema_version == "0.1"
    assert from_yaml.spec.execution.timeout_ms == 30000
    assert from_yaml.spec.execution.retry.initial_backoff_ms == 250
    assert from_yaml.spec.optimization.objective == "min_cost"

    # The YAML file intentionally omits optional defaults; model defaults fill them.
    assert from_json.spec.dataset.path == "cases.jsonl"


def test_relative_dataset_path_resolves_later_without_mutating_spec(tmp_path) -> None:
    spec_dir = tmp_path / "specs"
    spec_dir.mkdir()
    spec_path = spec_dir / "eval.yaml"
    spec_path.write_text(
        "\n".join(
            [
                "schema_version: '0.1'",
                "dataset:",
                "  path: ../data/cases.jsonl",
                "candidates:",
                "  - id: cheap",
                "    provider: fireworks",
                "    model: llama-8b",
            ]
        ),
        encoding="utf-8",
    )

    loaded = load_evaluation_spec(spec_path)
    assert loaded.spec.dataset.path == "../data/cases.jsonl"
    assert loaded.resolve_dataset_path() == (tmp_path / "data" / "cases.jsonl")


def test_rejects_unsupported_schema_version(tmp_path) -> None:
    doc = _minimal_document()
    doc["schema_version"] = "9.9"
    path = tmp_path / "eval.yaml"
    path.write_text(json.dumps(doc), encoding="utf-8")

    with pytest.raises(SpecLoadError, match="schema_version"):
        load_evaluation_spec(path)


def test_rejects_duplicate_candidate_ids() -> None:
    doc = _minimal_document()
    doc["candidates"].append({"id": "cheap", "provider": "openrouter", "model": "other"})
    with pytest.raises(ValidationError, match="unique"):
        EvaluationSpec.model_validate(doc)


def test_rejects_duplicate_validator_ids() -> None:
    doc = _minimal_document()
    doc["validators"].append({"id": "gate", "type": "contains"})
    with pytest.raises(ValidationError, match="unique"):
        EvaluationSpec.model_validate(doc)


def test_rejects_duplicate_constraint_ids() -> None:
    doc = _minimal_document()
    doc["constraints"].append({"id": "min-success", "metric": "max_cost_usd", "threshold": 1.0})
    with pytest.raises(ValidationError, match="unique"):
        EvaluationSpec.model_validate(doc)


def test_rejects_cascade_primary_not_in_candidates() -> None:
    doc = _minimal_document()
    doc["optimization"]["cascade"] = {"primary": "missing", "fallbacks": ["strong"]}
    with pytest.raises(ValidationError, match="candidate"):
        EvaluationSpec.model_validate(doc)


def test_rejects_cascade_fallback_not_in_candidates() -> None:
    doc = _minimal_document()
    doc["optimization"]["cascade"] = {"primary": "cheap", "fallbacks": ["missing"]}
    with pytest.raises(ValidationError, match="candidate"):
        EvaluationSpec.model_validate(doc)


def test_rejects_cascade_duplicate_fallback_ids() -> None:
    doc = _minimal_document()
    doc["optimization"]["cascade"] = {"primary": "cheap", "fallbacks": ["strong", "strong"]}
    with pytest.raises(ValidationError, match="cascade"):
        EvaluationSpec.model_validate(doc)


@pytest.mark.parametrize("validator_type", ["exact", "numeric", "python"])
def test_rejects_eval_only_routing_gates(validator_type: str) -> None:
    with pytest.raises(ValidationError, match="routing_gate"):
        ValidatorSpec(id="v", type=validator_type, routing_gate=True)


@pytest.mark.parametrize("validator_type", ["regex", "enum", "json_schema", "contains"])
def test_allows_runtime_capable_routing_gates(validator_type: str) -> None:
    spec = ValidatorSpec(id="v", type=validator_type, routing_gate=True)
    assert spec.runtime_capable is True
    assert spec.eval_only is False


def test_validator_exposes_runtime_capable() -> None:
    assert ValidatorSpec(id="v", type="regex").runtime_capable is True
    assert ValidatorSpec(id="v", type="exact").runtime_capable is False


def test_candidate_uses_parameters_not_params() -> None:
    candidate = CandidateSpec.model_validate(
        {"id": "c", "provider": "fireworks", "model": "m", "parameters": {"temperature": 0}}
    )
    assert candidate.parameters == {"temperature": 0}

    with pytest.raises(ValidationError, match="params"):
        CandidateSpec.model_validate(
            {"id": "c", "provider": "fireworks", "model": "m", "params": {"temperature": 0}}
        )


def test_test_case_serializes_nested_request() -> None:
    case = TestCase.model_validate(
        {
            "id": "case-1",
            "request": {"messages": [{"role": "user", "content": "hi"}]},
            "expected": {"ok": True},
        }
    )
    dumped = case.model_dump(mode="json")
    assert set(dumped) == {"id", "request", "expected", "metadata"}
    assert "messages" not in dumped
    assert dumped["request"]["messages"][0]["content"] == "hi"


def test_execution_requires_timeout_ms_and_backoff_ms_ranges() -> None:
    with pytest.raises(ValidationError, match="timeout_ms"):
        ExecutionSpec(timeout_ms=0)

    with pytest.raises(ValidationError, match="initial_backoff_ms"):
        RetrySpec(initial_backoff_ms=-1)

    with pytest.raises(ValidationError, match="max_backoff_ms"):
        RetrySpec(initial_backoff_ms=1000, max_backoff_ms=500)


def test_constraint_rate_thresholds_are_ranges() -> None:
    from inferencefit.contracts.optimization import ConstraintSpec

    with pytest.raises(ValidationError, match="between 0 and 1"):
        ConstraintSpec(id="c", metric="min_success_rate", threshold=1.5)
    with pytest.raises(ValidationError, match="between 0 and 1"):
        ConstraintSpec(id="c", metric="max_error_rate", threshold=-0.1)
    with pytest.raises(ValidationError, match="non-negative"):
        ConstraintSpec(id="c", metric="max_p95_latency_ms", threshold=-1)


def test_optimization_objective_uses_binding_names() -> None:
    for objective in ["min_cost", "min_latency", "max_quality", "max_reliability", "balanced"]:
        spec = OptimizationSpec(objective=objective)
        assert spec.objective == objective

    with pytest.raises(ValidationError, match="objective"):
        OptimizationSpec(objective="max_cost")


def test_loader_rejects_duplicate_yaml_keys(tmp_path) -> None:
    path = tmp_path / "dup.yaml"
    path.write_text(
        "\n".join(
            [
                "schema_version: '0.1'",
                "dataset:",
                "  path: cases.jsonl",
                "candidates:",
                "  - id: cheap",
                "    provider: fireworks",
                "    model: llama-8b",
                "schema_version: '0.1'",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(SpecLoadError, match="duplicate"):
        load_evaluation_spec(path)
