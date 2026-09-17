from __future__ import annotations

import sys
import types

import httpx
import pytest

from inferencefit.contracts import (
    CandidateSpec,
    CandidateSummary,
    EvaluationSpec,
    Observation,
    TestCase,
    TokenUsage,
    ValidatorSpec,
)
from inferencefit.execution.runner import _execute
from inferencefit.metrics import aggregate_candidate
from inferencefit.optimization import pareto_frontier, rank_summaries
from inferencefit.providers import OpenAICompatibleProvider, ProviderError, ProviderResponse
from inferencefit.validators import evaluate_validators


def _case(expected=None) -> TestCase:
    return TestCase.model_validate(
        {
            "id": "c",
            "request": {"messages": [{"role": "user", "content": "test"}]},
            "expected": expected,
        }
    )


@pytest.mark.parametrize(
    ("validator", "raw"),
    [
        (ValidatorSpec(id="r", type="regex", config={"pattern": "ell"}), "hello"),
        (ValidatorSpec(id="e", type="enum", config={"values": ["yes"]}), "yes"),
        (ValidatorSpec(id="c", type="contains", config={"value": "world"}), "hello world"),
        (
            ValidatorSpec(
                id="n",
                type="numeric",
                target="/value",
                reference="/value",
                config={"tolerance": 0.1},
            ),
            '{"value": 1.05}',
        ),
    ],
)
def test_remaining_builtin_validators(validator, raw):
    result = evaluate_validators([validator], _case({"value": 1.0}), raw)
    assert result.passed is True


def test_local_python_validator_receives_candidate_response():
    module = types.ModuleType("inferencefit_test_validator")

    def validate(test_case, response):
        return response.raw_output == "ok" and response.parsed_output is None

    module.validate = validate
    sys.modules[module.__name__] = module
    try:
        spec = ValidatorSpec(
            id="python", type="python", config={"callable": f"{module.__name__}:validate"}
        )
        assert evaluate_validators([spec], _case(), "ok").passed is True
    finally:
        sys.modules.pop(module.__name__, None)


@pytest.mark.asyncio
async def test_retryable_provider_failure_retries_but_semantic_failure_does_not():
    spec = EvaluationSpec.model_validate(
        {
            "dataset": {"path": "unused"},
            "candidates": [{"id": "c", "provider": "fixture", "model": "m"}],
            "execution": {
                "retry": {"max_attempts": 3, "initial_backoff_ms": 0, "max_backoff_ms": 0}
            },
        }
    )
    candidate = spec.candidates[0]

    class Flaky:
        attempts = 0

        async def complete(self, candidate, test_case, repetition):
            self.attempts += 1
            if self.attempts < 3:
                raise ProviderError("temporary", retryable=True)
            return ProviderResponse(raw_output="ok", latency_ms=1)

    flaky = Flaky()
    result = await _execute(candidate, _case(), 0, spec, flaky)
    assert result.provider_status == "success"
    assert result.provider_attempts == 3

    class Permanent:
        attempts = 0

        async def complete(self, candidate, test_case, repetition):
            self.attempts += 1
            raise ProviderError("bad request", retryable=False)

    permanent = Permanent()
    result = await _execute(candidate, _case(), 0, spec, permanent)
    assert result.provider_status == "error"
    assert permanent.attempts == 1


def test_unknown_cost_is_preserved_and_unrankable():
    observation = Observation(
        case_id="c",
        candidate_id="x",
        repetition=0,
        provider_status="success",
        raw_output="ok",
        usage=TokenUsage(input_tokens=1, output_tokens=1),
        latency_ms=1,
        cost_usd=None,
    )
    summary = aggregate_candidate("x", [observation])
    assert summary.total_cost_usd is None
    summary.eligible = True
    assert rank_summaries([summary], "min_cost") == []
    assert "known" in summary.unrankable_reason


def test_every_objective_and_balanced_v1_are_deterministic():
    a = CandidateSummary(
        id="a",
        validation_pass_rate=0.8,
        provider_success_rate=0.9,
        end_to_end_success_rate=0.8,
        cost_per_1k_requests_usd=1,
        p95_latency_ms=100,
    )
    b = CandidateSummary(
        id="b",
        validation_pass_rate=0.9,
        provider_success_rate=0.8,
        end_to_end_success_rate=0.9,
        cost_per_1k_requests_usd=2,
        p95_latency_ms=50,
    )
    assert rank_summaries([a.model_copy(), b.model_copy()], "min_cost")[0].id == "a"
    assert rank_summaries([a.model_copy(), b.model_copy()], "min_latency")[0].id == "b"
    assert rank_summaries([a.model_copy(), b.model_copy()], "max_quality")[0].id == "b"
    assert rank_summaries([a.model_copy(), b.model_copy()], "max_reliability")[0].id == "a"
    ranked = rank_summaries([a.model_copy(), b.model_copy()], "balanced")
    assert [item.id for item in ranked] == ["a", "b"]
    assert ranked[0].objective_score == pytest.approx(0.75)


def test_unknown_dimension_prevents_false_pareto_dominance():
    known = CandidateSummary(
        id="known",
        validation_pass_rate=0.5,
        end_to_end_success_rate=0.5,
        provider_success_rate=0.5,
        cost_per_1k_requests_usd=1,
        p95_latency_ms=10,
    )
    unknown = known.model_copy(
        update={
            "id": "unknown",
            "validation_pass_rate": 1,
            "end_to_end_success_rate": 1,
            "provider_success_rate": 1,
            "cost_per_1k_requests_usd": None,
        }
    )
    assert pareto_frontier([known, unknown]) == ["known", "unknown"]


@pytest.mark.asyncio
async def test_openai_compatible_adapter_normalizes_response(respx_mock):
    route = respx_mock.post("https://example.test/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "model": "served-model",
                "choices": [{"message": {"content": "answer"}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 2},
            },
        )
    )
    candidate = CandidateSpec(
        id="x", provider="custom", model="requested", base_url="https://example.test/v1"
    )
    result = await OpenAICompatibleProvider("token").complete(candidate, _case(), 0)
    assert result.raw_output == "answer"
    assert result.input_tokens == 3
    assert result.output_tokens == 2
    assert route.calls[0].request.headers["authorization"] == "Bearer token"
