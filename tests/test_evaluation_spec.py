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


def _candidate_error_messages(exc: ValidationError) -> list[str]:
    """Return only the safe ValueError categories, never echoing input values."""
    return [error["msg"] for error in exc.errors()]


def test_custom_candidate_requires_explicit_base_url() -> None:
    with pytest.raises(ValidationError, match="custom provider requires base_url"):
        CandidateSpec.model_validate({"id": "c", "provider": "custom", "model": "m"})


@pytest.mark.parametrize("blank", ["", "   ", "\t", "\n "])
def test_custom_candidate_rejects_blank_base_url_without_echo(blank: str) -> None:
    with pytest.raises(ValidationError, match="custom provider requires base_url") as exc_info:
        CandidateSpec.model_validate(
            {"id": "c", "provider": "custom", "model": "m", "base_url": blank}
        )

    messages = _candidate_error_messages(exc_info.value)
    assert messages == ["Value error, custom provider requires base_url"]


@pytest.mark.parametrize(
    "base_url",
    [
        "http://localhost:8000/v1",
        "http://127.0.0.1:11434/v1/",
        "http://[::1]:8000/v1",
        "https://gateway.example.com/api",
        "https://gateway.example.com",
        "https://gateway.example.com/v1/",
    ],
)
def test_custom_candidate_accepts_valid_base_urls(base_url: str) -> None:
    candidate = CandidateSpec.model_validate(
        {"id": "c", "provider": "custom", "model": "some/model-name", "base_url": base_url}
    )
    assert candidate.base_url == base_url


def test_custom_candidate_preserves_model_credential_and_pricing() -> None:
    candidate = CandidateSpec.model_validate(
        {
            "id": "c",
            "provider": "custom",
            "model": "some/model-name",
            "base_url": "https://gateway.example.com/v1",
            "credential_ref": "example-main",
            "pricing": {"input_per_million": 1.0, "output_per_million": 2.0},
            "parameters": {"max_tokens": 64},
        }
    )
    assert candidate.model == "some/model-name"
    assert candidate.credential_ref == "example-main"
    assert candidate.pricing is not None
    assert candidate.pricing.input_per_million == 1.0
    assert candidate.pricing.output_per_million == 2.0
    assert candidate.parameters == {"max_tokens": 64}


@pytest.mark.parametrize(
    "provider",
    ["fireworks", "openrouter", "openai", "gemini", "ollama", "vllm", "opneai", "totally-unknown"],
)
def test_providers_without_base_url_remain_valid(provider: str) -> None:
    candidate = CandidateSpec.model_validate({"id": "c", "provider": provider, "model": "m"})
    assert candidate.base_url is None


def test_named_provider_with_explicit_base_url_remains_valid() -> None:
    candidate = CandidateSpec.model_validate(
        {
            "id": "c",
            "provider": "openai",
            "model": "gpt-x",
            "base_url": "https://proxy.example.com/v1",
        }
    )
    assert candidate.base_url == "https://proxy.example.com/v1"


@pytest.mark.parametrize(
    "base_url",
    [
        "ftp://gateway.example.com/v1",
        "gateway.example.com/v1",
        "//gateway.example.com/v1",
        "https://",
        "http://:8000/v1",
        "http://localhost:notaport/v1",
        "http://localhost:99999/v1",
        "https://user:pass@gateway.example.com/v1",
        "https://user@gateway.example.com/v1",
        "https://gateway.example.com/v1?token=abc",
        "https://gateway.example.com/v1#frag",
        "https://gateway.example.com/v1/chat/completions",
        "https://gateway.example.com/chat/completions/",
        "https://gateway.example.com/V1/Chat/Completions",
        "https://gateway.example.com/v1/ chat",
        "https://gateway.example.com/v1/pa\tth",
    ],
)
def test_malformed_base_url_rejected_without_echoing_url(base_url: str) -> None:
    with pytest.raises(ValidationError, match="invalid base_url") as exc_info:
        CandidateSpec.model_validate(
            {"id": "c", "provider": "custom", "model": "m", "base_url": base_url}
        )

    messages = _candidate_error_messages(exc_info.value)
    assert messages == ["Value error, invalid base_url"]
    # The safe category never embeds the offending URL text.
    assert base_url.strip() not in " ".join(messages)


def test_malformed_base_url_on_named_provider_also_rejected() -> None:
    with pytest.raises(ValidationError, match="invalid base_url"):
        CandidateSpec.model_validate(
            {
                "id": "c",
                "provider": "openai",
                "model": "gpt-x",
                "base_url": "https://gateway.example.com/v1/chat/completions",
            }
        )


def test_blank_base_url_on_named_provider_rejected() -> None:
    with pytest.raises(ValidationError, match="invalid base_url"):
        CandidateSpec.model_validate(
            {"id": "c", "provider": "fireworks", "model": "m", "base_url": "   "}
        )


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
