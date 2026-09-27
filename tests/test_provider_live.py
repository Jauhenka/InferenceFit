"""Opt-in live smoke checks for the built-in providers."""

import json
import os
from pathlib import Path

import pytest

from inferencefit import benchmark


async def _run_live_benchmark(tmp_path: Path, *, provider: str, model: str, parameters: dict):
    dataset_path = tmp_path / "dataset.jsonl"
    dataset_path.write_text(
        json.dumps(
            {
                "id": "smoke",
                "request": {"messages": [{"role": "user", "content": "Reply with only OK."}]},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    spec_path = tmp_path / "eval.yaml"
    spec_path.write_text(
        "schema_version: '0.1'\n"
        "dataset: {path: dataset.jsonl}\n"
        "candidates:\n"
        "  - id: live-smoke\n"
        f"    provider: {provider}\n"
        f"    model: {model}\n"
        f"    parameters: {json.dumps(parameters)}\n"
        "optimization: {objective: max_quality}\n"
        "execution: {retry: {max_attempts: 1}}\n",
        encoding="utf-8",
    )

    result = await benchmark(spec_path, output_root=tmp_path / "runs")
    run_dir = tmp_path / "runs" / result.run_id
    observation_lines = (run_dir / "observations.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(observation_lines) == 1
    observation = json.loads(observation_lines[0])
    assert observation["provider_status"] == "success"
    assert observation["raw_output"].strip()
    usage = observation["usage"]
    if any(value is not None for value in usage.values()):
        assert any(value > 0 for value in usage.values() if value is not None)

    persisted_result = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
    assert result.status == persisted_result["status"] == "completed"
    assert persisted_result["candidate_summaries"][0]["provider_success_count"] == 1


@pytest.mark.provider_live
@pytest.mark.asyncio
async def test_openrouter_live_benchmark(tmp_path):
    if not os.environ.get("OPEN_ROUTER_API_KEY"):
        pytest.skip("OPEN_ROUTER_API_KEY is not set")
    model = os.environ.get("OPEN_ROUTER_TEST_MODEL", "openrouter/free")
    await _run_live_benchmark(
        tmp_path, provider="openrouter", model=model, parameters={"max_tokens": 32}
    )


@pytest.mark.provider_live
@pytest.mark.asyncio
async def test_gemini_live_benchmark(tmp_path):
    if not os.environ.get("GEMINI_API_KEY"):
        pytest.skip("GEMINI_API_KEY is not set")
    model = os.environ.get("GEMINI_TEST_MODEL", "gemini-3.5-flash-lite")
    await _run_live_benchmark(
        tmp_path, provider="gemini", model=model, parameters={"max_tokens": 32}
    )


@pytest.mark.provider_live
@pytest.mark.asyncio
async def test_openai_live_benchmark(tmp_path):
    if not os.environ.get("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY is not set")
    model = os.environ.get("OPENAI_TEST_MODEL", "gpt-6-luna")
    await _run_live_benchmark(
        tmp_path, provider="openai", model=model, parameters={"max_output_tokens": 64}
    )
