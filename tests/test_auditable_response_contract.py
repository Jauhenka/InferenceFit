"""Optional provider-native metadata uses the existing observation artifact path."""

import json

import pytest

from inferencefit.contracts import EvaluationSpec, Observation
from inferencefit.contracts import TestCase as Case
from inferencefit.execution.runner import _execute
from inferencefit.providers import ProviderResponse
from inferencefit.storage import FilesystemArtifactStore


@pytest.mark.asyncio
async def test_native_metadata_survives_runner_jsonl_and_reload(tmp_path):
    spec = EvaluationSpec.model_validate(
        {
            "dataset": {"path": "unused"},
            "candidates": [{"id": "native", "provider": "anthropic", "model": "opaque"}],
        }
    )
    case = Case.model_validate(
        {"id": "c", "request": {"messages": [{"role": "user", "content": "hello"}]}}
    )
    native = {
        "content": [
            {"type": "thinking", "thinking": "visible reasoning"},
            {"type": "text", "text": "answer"},
        ],
        "usage": {"input_tokens": 2, "cache_read_input_tokens": 3, "output_tokens": 10},
        "stop_reason": "end_turn",
    }

    class NativeProvider:
        async def complete(self, candidate, test_case, repetition):
            return ProviderResponse(
                raw_output="answer",
                latency_ms=1,
                input_tokens=5,
                output_tokens=10,
                total_tokens=15,
                provider="anthropic",
                model="served",
                raw_response=native,
                finish_reason="stop",
                provider_finish_reason="end_turn",
                provider_request_id="req-test",
                reasoning_tokens=7,
                reasoning_content="visible reasoning",
                usage_details=native["usage"],
            )

    observation = await _execute(spec.candidates[0], case, 0, spec, NativeProvider())
    assert observation.raw_response == native
    assert observation.finish_reason == "stop"
    assert observation.provider_finish_reason == "end_turn"
    assert observation.provider_request_id == "req-test"
    assert observation.reasoning_tokens == 7
    assert observation.reasoning_content == "visible reasoning"
    assert observation.usage_details == native["usage"]
    assert observation.usage.output_tokens == 10  # Total output, not final-answer-only tokens.

    store = FilesystemArtifactStore(tmp_path)
    store.create("audit-run")
    store.append_observation("audit-run", observation)
    (reloaded,) = store.observations("audit-run")
    assert reloaded == observation
    persisted = json.loads((tmp_path / "audit-run" / "observations.jsonl").read_text())
    for name in (
        "raw_response",
        "finish_reason",
        "provider_finish_reason",
        "provider_request_id",
        "reasoning_tokens",
        "reasoning_content",
        "usage_details",
    ):
        assert persisted[name] == getattr(observation, name)


def test_old_schema_observation_loads_with_missing_native_metadata():
    old = {
        "schema_version": "0.1",
        "case_id": "c",
        "candidate_id": "legacy",
        "repetition": 0,
        "provider_status": "success",
        "raw_output": "answer",
        "usage": {"input_tokens": 2, "output_tokens": 3},
    }
    loaded = Observation.model_validate_json(json.dumps(old))
    assert loaded.schema_version == "0.1"
    for name in (
        "raw_response",
        "finish_reason",
        "provider_finish_reason",
        "provider_request_id",
        "reasoning_tokens",
        "reasoning_content",
        "usage_details",
    ):
        assert getattr(loaded, name) is None
