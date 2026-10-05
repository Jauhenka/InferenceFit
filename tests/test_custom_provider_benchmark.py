"""Offline public-benchmark coverage for the generic ``custom`` provider."""

import asyncio
import json
import secrets

import httpx
import pytest

from inferencefit import benchmark

_ARTIFACTS = {
    "spec.yaml",
    "dataset.jsonl",
    "observations.jsonl",
    "manifest.json",
    "result.json",
    "routing-policy.yaml",
    "summary.md",
}


def _write_case(tmp_path):
    (tmp_path / "dataset.jsonl").write_text(
        json.dumps(
            {
                "id": "c",
                "request": {"messages": [{"role": "user", "content": "classify"}]},
                "expected": {"category": "a"},
            }
        )
        + "\n",
        encoding="utf-8",
    )


def _observations(run_dir):
    return [
        json.loads(line)
        for line in (run_dir / "observations.jsonl").read_text(encoding="utf-8").splitlines()
    ]


async def test_authenticated_custom_benchmark_masks_resolved_secret(
    tmp_path, monkeypatch, respx_mock, caplog
):
    secret = f"custom-{secrets.token_hex(16)}"
    monkeypatch.setenv("INFERENCEFIT_CREDENTIAL_CUSTOM_TEST", secret)
    _write_case(tmp_path)
    spec_path = tmp_path / "eval.yaml"
    spec_path.write_text(
        """schema_version: '0.1'
dataset: {path: dataset.jsonl}
candidates:
  - id: custom
    provider: custom
    model: requested-model
    base_url: https://custom.example.test/v1
    credential_ref: custom-test
    parameters: {max_tokens: 64}
    pricing: {input_per_million: 3, output_per_million: 5}
validators:
  - {id: correct, type: exact, target: /category, reference: /category}
constraints: {min_success_rate: 1}
optimization: {objective: min_cost}
execution: {retry: {max_attempts: 1}}
""",
        encoding="utf-8",
    )
    output = '{"category":"a"}'
    route = respx_mock.post("https://custom.example.test/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "model": "served-model",
                "choices": [{"message": {"content": output}}],
                "usage": {
                    "prompt_tokens": 2,
                    "completion_tokens": 3,
                    "total_tokens": 5,
                    "cost": 99,
                },
            },
        )
    )

    result = await benchmark(spec_path, output_root=tmp_path / "runs", run_id="custom-auth")
    run_dir = tmp_path / "runs" / result.run_id
    (row,) = _observations(run_dir)
    assert row["provider_status"] == "success"
    assert row["raw_output"] == output
    assert row["validation"]["passed"] is True
    assert (row["provider"], row["model"], row["provider_backend"]) == (
        "custom",
        "served-model",
        None,
    )
    assert row["usage"] == {"input_tokens": 2, "output_tokens": 3, "total_tokens": 5}
    assert row["cost_source"] == "configured_pricing"
    assert row["cost_usd"] == pytest.approx((2 * 3 + 3 * 5) / 1_000_000)
    assert row["latency_ms"] >= 0
    assert result.candidate_summaries[0].provider_success_rate == 1
    assert route.calls[0].request.headers["Authorization"] == f"Bearer {secret}"
    request_body = json.loads(route.calls[0].request.content)
    assert request_body == {
        "model": "requested-model",
        "messages": [{"role": "user", "content": "classify"}],
        "max_tokens": 64,
    }
    assert result.candidate_summaries[0].total_cost_usd == pytest.approx(row["cost_usd"])
    assert secret not in caplog.text

    # The resolved secret value is absent from every persisted artifact; the
    # opaque ``credential_ref`` is intentionally not asserted absent.
    assert {path.name for path in run_dir.iterdir()} == _ARTIFACTS
    for path in run_dir.iterdir():
        assert secret not in path.read_text(encoding="utf-8")


async def test_credentialless_custom_benchmark_reports_unknown_cost(tmp_path, respx_mock):
    _write_case(tmp_path)
    spec_path = tmp_path / "eval.yaml"
    spec_path.write_text(
        """schema_version: '0.1'
dataset: {path: dataset.jsonl}
candidates:
  - id: public
    provider: custom
    model: public-model
    base_url: https://public.example.test/v1
validators:
  - {id: correct, type: exact, target: /category, reference: /category}
execution: {retry: {max_attempts: 1}}
""",
        encoding="utf-8",
    )
    output = '{"category":"a"}'
    route = respx_mock.post("https://public.example.test/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={"choices": [{"message": {"content": output}}]})
    )

    result = await benchmark(spec_path, output_root=tmp_path / "runs", run_id="custom-public")
    run_dir = tmp_path / "runs" / result.run_id
    (row,) = _observations(run_dir)
    assert row["provider_status"] == "success"
    assert row["model"] == "public-model"
    assert row["usage"] == {"input_tokens": None, "output_tokens": None, "total_tokens": None}
    assert row["cost_usd"] is None
    assert row["cost_source"] is None
    assert "Authorization" not in route.calls[0].request.headers
    assert {path.name for path in run_dir.iterdir()} == _ARTIFACTS


async def test_custom_benchmark_retries_rate_limit_then_succeeds(tmp_path, respx_mock):
    _write_case(tmp_path)
    spec_path = tmp_path / "eval.yaml"
    spec_path.write_text(
        """schema_version: '0.1'
dataset: {path: dataset.jsonl}
candidates:
  - {id: retry, provider: custom, model: retry-model, base_url: https://retry.example.test/v1}
execution: {retry: {max_attempts: 2, initial_backoff_ms: 0, max_backoff_ms: 0}}
""",
        encoding="utf-8",
    )
    calls = 0

    def respond(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, text="secret response body")
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    respx_mock.post("https://retry.example.test/v1/chat/completions").mock(side_effect=respond)
    result = await benchmark(spec_path, output_root=tmp_path / "runs", run_id="custom-retry")
    (row,) = _observations(tmp_path / "runs" / result.run_id)
    assert calls == 2
    assert row["provider_status"] == "success"
    assert row["provider_attempts"] == 2
    assert "secret response body" not in json.dumps(row)


async def test_custom_benchmark_uses_common_total_timeout(tmp_path, respx_mock):
    _write_case(tmp_path)
    spec_path = tmp_path / "eval.yaml"
    spec_path.write_text(
        """schema_version: '0.1'
dataset: {path: dataset.jsonl}
candidates:
  - {id: slow, provider: custom, model: slow-model, base_url: https://slow.example.test/v1}
execution: {timeout_ms: 5, retry: {max_attempts: 2, initial_backoff_ms: 0, max_backoff_ms: 0}}
""",
        encoding="utf-8",
    )

    async def respond(request):
        await asyncio.sleep(0.05)
        return httpx.Response(200, json={"choices": [{"message": {"content": "late"}}]})

    respx_mock.post("https://slow.example.test/v1/chat/completions").mock(side_effect=respond)
    result = await benchmark(spec_path, output_root=tmp_path / "runs", run_id="custom-timeout")
    (row,) = _observations(tmp_path / "runs" / result.run_id)
    assert row["provider_status"] == "error"
    assert row["provider_attempts"] == 2
    assert row["error"]["kind"] == "timeout"
    assert row["error"]["retryable"] is True
