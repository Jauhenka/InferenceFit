"""One normal benchmark containing a fixture and a Cloud candidate."""

from __future__ import annotations

import json

import httpx
import pytest

from inferencefit import benchmark


@pytest.mark.asyncio
async def test_mixed_fixture_and_cloud_use_one_runner_and_artifact_format(
    tmp_path, monkeypatch, respx_mock
):
    token = "ifc_private_test_token"
    origin = "http://127.0.0.1:8765"
    monkeypatch.setenv("INFERENCEFIT_CLOUD_TOKEN", token)
    monkeypatch.setenv("INFERENCEFIT_CLOUD_API_URL", origin)
    (tmp_path / "dataset.jsonl").write_text(
        json.dumps(
            {
                "id": "c1",
                "request": {"messages": [{"role": "user", "content": "Classify alpha"}]},
                "expected": {"label": "alpha"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "fixture.jsonl").write_text(
        json.dumps(
            {
                "case_id": "c1",
                "raw_output": '{"label":"alpha"}',
                "input_tokens": 4,
                "output_tokens": 5,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    spec = tmp_path / "eval.yaml"
    spec.write_text(
        """schema_version: '0.1'
dataset: {path: dataset.jsonl}
candidates:
  - id: local
    provider: fixture
    model: sample
    parameters: {fixture_path: fixture.jsonl}
    pricing: {input_per_million: 1, output_per_million: 2}
  - id: hosted
    provider: inferencefit-cloud
    model: catalog-model-placeholder
    parameters: {max_tokens: 16}
validators:
  - {id: label, type: exact, target: /label, reference: /label}
optimization: {objective: min_cost}
execution: {retry: {max_attempts: 1}}
""",
        encoding="utf-8",
    )
    completion = respx_mock.post(f"{origin}/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "request_id": "request-cloud-1",
                "model": "catalog-model-placeholder",
                "choices": [
                    {
                        "message": {"role": "assistant", "content": '{"label":"alpha"}'},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 6, "completion_tokens": 7, "total_tokens": 13},
            },
        )
    )
    status = respx_mock.get(f"{origin}/v1/requests/request-cloud-1").mock(
        return_value=httpx.Response(
            200,
            json={
                "request_id": "request-cloud-1",
                "status": "settled",
                "charged_micro_usd": 321,
            },
        )
    )
    result = await benchmark(spec, output_root=tmp_path / "runs", run_id="mixed")
    run_dir = tmp_path / "runs/mixed"
    observations = {
        item["candidate_id"]: item
        for item in (
            json.loads(line)
            for line in (run_dir / "observations.jsonl").read_text(encoding="utf-8").splitlines()
        )
    }
    assert set(observations) == {"local", "hosted"}
    assert all(row["validation"]["passed"] for row in observations.values())
    assert observations["local"]["cost_usd"] == pytest.approx(0.000014)
    assert observations["hosted"]["cost_usd"] == pytest.approx(0.000321)
    assert observations["hosted"]["cost_source"] == "provider_reported"
    assert observations["hosted"]["provider_request_id"] == "request-cloud-1"
    assert observations["hosted"]["provider"] == "inferencefit-cloud"
    assert completion.call_count == status.call_count == 1
    assert completion.calls[0].request.headers["idempotency-key"].startswith("ifc-")
    assert len(result.candidate_summaries) == 2
    for path in run_dir.iterdir():
        assert token not in path.read_text(encoding="utf-8")
    before = (run_dir / "observations.jsonl").read_bytes()
    await benchmark(spec, output_root=tmp_path / "runs", resume="mixed")
    assert (run_dir / "observations.jsonl").read_bytes() == before
    assert completion.call_count == status.call_count == 1
