"""Public benchmark integration with only the provider HTTP boundary mocked."""

import ast
import inspect
import json
from datetime import datetime

import httpx
import pytest

import inferencefit
from inferencefit import benchmark


@pytest.mark.asyncio
async def test_three_provider_benchmark_persists_metadata_and_safe_artifacts(
    tmp_path, monkeypatch, respx_mock
):
    credentials = {
        "ROUTER_TEST": "router-integration-secret",
        "GEMINI_TEST": "gemini-integration-secret",
        "OPENAI_TEST": "openai-integration-secret",
    }
    for reference, token in credentials.items():
        monkeypatch.setenv(f"INFERENCEFIT_CREDENTIAL_{reference}", token)
    # A sentinel catches an independent version literal in the manifest.
    monkeypatch.setattr(inferencefit, "__version__", "test-package-version")
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
    spec_path = tmp_path / "eval.yaml"
    spec_path.write_text(
        """schema_version: '0.1'
dataset: {path: dataset.jsonl}
candidates:
  - id: router
    provider: openrouter
    model: vendor/requested
    credential_ref: router-test
    pricing: {input_per_million: 100, output_per_million: 100}
  - id: gemini
    provider: gemini
    model: gemini-requested
    credential_ref: gemini-test
    pricing: {input_per_million: 1, output_per_million: 2}
  - id: openai
    provider: openai
    model: openai-requested
    credential_ref: openai-test
validators:
  - {id: correct, type: exact, target: /category, reference: /category}
constraints: {min_success_rate: 1}
optimization: {objective: min_cost}
execution: {retry: {max_attempts: 1}}
""",
        encoding="utf-8",
    )
    output = '{"category":"a"}'
    router_route = respx_mock.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "model": "vendor/served",
                "provider": "ExampleBackend",
                "choices": [{"message": {"content": output}}],
                "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5, "cost": 0},
            },
        )
    )
    gemini_route = respx_mock.post(
        "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "model": "gemini-served",
                "choices": [{"message": {"content": output}}],
                "usage": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6},
            },
        )
    )
    openai_route = respx_mock.post("https://api.openai.com/v1/responses").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "resp_test",
                "object": "response",
                "status": "completed",
                "model": "openai-served",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {"type": "output_text", "text": output, "annotations": []},
                        ],
                    }
                ],
                "usage": {"input_tokens": 7, "output_tokens": 3, "total_tokens": 10},
            },
        )
    )

    result = await benchmark(spec_path, output_root=tmp_path / "runs", run_id="three-providers")
    run_dir = tmp_path / "runs" / result.run_id
    observations = {
        row["candidate_id"]: row
        for row in (
            json.loads(line)
            for line in (run_dir / "observations.jsonl").read_text(encoding="utf-8").splitlines()
        )
    }
    assert set(observations) == {"router", "gemini", "openai"}
    for row in observations.values():
        assert row["schema_version"] == "0.1"
        assert row["provider_status"] == "success"
        assert row["raw_output"] == output
        assert row["validation"]["passed"] is True
        assert row["provider_attempts"] == 1
    for candidate_id, provider, model, counts, cost, source, backend in [
        (
            "router",
            "openrouter",
            "vendor/served",
            (2, 3, 5),
            0,
            "provider_reported",
            "ExampleBackend",
        ),
        ("gemini", "gemini", "gemini-served", (4, 2, 6), 0.000008, "configured_pricing", None),
        ("openai", "openai", "openai-served", (7, 3, 10), None, None, None),
    ]:
        row = observations[candidate_id]
        assert (row["provider"], row["model"], row["provider_backend"]) == (
            provider,
            model,
            backend,
        )
        assert row["usage"] == dict(
            zip(["input_tokens", "output_tokens", "total_tokens"], counts, strict=True)
        )
        assert row["cost_source"] == source
        assert row["cost_usd"] == (pytest.approx(cost) if cost is not None else None)
    assert router_route.calls[0].request.headers["X-OpenRouter-Metadata"] == "enabled"
    for route, token in zip(
        [router_route, gemini_route, openai_route], credentials.values(), strict=True
    ):
        assert route.calls[0].request.headers["Authorization"] == f"Bearer {token}"
    assert json.loads(openai_route.calls[0].request.content)["store"] is False

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    persisted_result = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == persisted_result["schema_version"] == "0.1"
    assert manifest["status"] == persisted_result["status"] == result.status == "completed"
    assert manifest["planned_observations"] == 3
    assert manifest["inferencefit_version"] == "test-package-version"
    assert datetime.fromisoformat(manifest["completed_at"]) == datetime.fromisoformat(
        persisted_result["completed_at"]
    )
    assert persisted_result["provenance"] == {
        "spec_hash": manifest["spec_hash"],
        "dataset_hash": manifest["dataset_hash"],
    }
    assert persisted_result["recommendation"] == result.recommendation == "router"
    assert all(
        item["provider_success_count"] == 1 for item in persisted_result["candidate_summaries"]
    )
    summaries = {summary.id: summary for summary in result.candidate_summaries}
    assert {
        candidate_id: (summary.total_input_tokens, summary.total_output_tokens)
        for candidate_id, summary in summaries.items()
    } == {"router": (2, 3), "gemini": (4, 2), "openai": (7, 3)}
    assert {path.name for path in run_dir.iterdir()} == {
        "spec.yaml",
        "dataset.jsonl",
        "observations.jsonl",
        "manifest.json",
        "result.json",
        "routing-policy.yaml",
        "summary.md",
    }
    for path in run_dir.iterdir():
        text = path.read_text(encoding="utf-8")
        assert "credential_ref" not in text
        for token in credentials.values():
            assert token not in text

    before = (run_dir / "observations.jsonl").read_bytes()
    resumed = await benchmark(spec_path, output_root=tmp_path / "runs", resume=result.run_id)
    assert resumed.recommendation == "router"
    assert (run_dir / "observations.jsonl").read_bytes() == before
    assert [route.call_count for route in [router_route, gemini_route, openai_route]] == [1, 1, 1]


def test_benchmark_has_no_provider_dispatch_branches():
    # Architectural requirement: vendor dispatch belongs to the registry.
    tree = ast.parse(inspect.getsource(benchmark))
    branches = [node for node in ast.walk(tree) if isinstance(node, (ast.If, ast.IfExp))]
    for branch in branches:
        assert not any(
            isinstance(node, ast.Attribute) and node.attr == "provider"
            for node in ast.walk(branch.test)
        ), "benchmark must delegate provider selection to the registry"
