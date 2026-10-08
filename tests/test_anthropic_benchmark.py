"""Offline end-to-end coverage of the public Anthropic benchmark path."""

import json
import secrets

import httpx
import pytest

from inferencefit import benchmark

URL = "https://api.anthropic.com/v1/messages"


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["anthropic", "claude"])
@pytest.mark.parametrize("with_pricing", [False, True])
async def test_anthropic_benchmark_uses_shared_artifacts_and_cost_pipeline(
    tmp_path, monkeypatch, respx_mock, caplog, provider, with_pricing
):
    secret = f"anthropic-{secrets.token_hex(16)}"
    monkeypatch.setenv("ANTHROPIC_API_KEY", secret)
    (tmp_path / "cases.jsonl").write_text(
        json.dumps(
            {
                "id": "case",
                "request": {"messages": [{"role": "user", "content": "classify"}]},
                "expected": {"category": "a"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    pricing = "    pricing: {input_per_million: 3, output_per_million: 5}\n" if with_pricing else ""
    (tmp_path / "eval.yaml").write_text(
        f"""schema_version: '0.1'
dataset: {{path: cases.jsonl}}
candidates:
  - id: claude-candidate
    provider: {provider}
    model: opaque-model-id
    parameters: {{max_tokens: 32}}
{pricing}validators:
  - {{id: correct, type: exact, target: /category, reference: /category}}
execution: {{retry: {{max_attempts: 1}}}}
""",
        encoding="utf-8",
    )
    output = '{"category":"a"}'
    route = respx_mock.post(URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "model": "served-model-id",
                "content": [{"type": "text", "text": output}],
                "usage": {"input_tokens": 2, "output_tokens": 3},
            },
        )
    )
    result = await benchmark(
        tmp_path / "eval.yaml", output_root=tmp_path / "runs", run_id="anthropic-run"
    )
    run_dir = tmp_path / "runs" / result.run_id
    (row,) = [
        json.loads(line)
        for line in (run_dir / "observations.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert row["provider_status"] == "success"
    assert row["validation"]["passed"] is True
    assert (row["provider"], row["model"], row["raw_output"]) == (
        "anthropic",
        "served-model-id",
        output,
    )
    assert row["usage"] == {"input_tokens": 2, "output_tokens": 3, "total_tokens": 5}
    assert route.calls[0].request.headers["x-api-key"] == secret
    assert result.candidate_summaries[0].provider_success_rate == 1
    if with_pricing:
        assert row["cost_source"] == "configured_pricing"
        assert row["cost_usd"] == pytest.approx((2 * 3 + 3 * 5) / 1_000_000)
    else:
        assert row["cost_source"] is None
        assert row["cost_usd"] is None

    assert secret not in caplog.text
    for path in run_dir.iterdir():
        assert secret not in path.read_text(encoding="utf-8")
