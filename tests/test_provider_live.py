"""Opt-in live smoke checks for the built-in providers."""

import json
import os
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from inferencefit import benchmark


def _select_live_model(provider: str, catalog: object, override: str | None = None) -> str | None:
    """Choose a low-cost currently served text model for opt-in smoke only."""
    if provider == "chutes" and override:
        return override
    if not isinstance(catalog, dict) or not isinstance(catalog.get("data"), list):
        return None
    if provider == "nosana":
        if not override:
            return None
        return next(
            (
                override
                for item in catalog["data"]
                if isinstance(item, dict)
                and item.get("id") == override
                and item.get("available") is True
            ),
            None,
        )
    if provider != "chutes":
        return None
    choices: list[tuple[Decimal, str]] = []
    for item in catalog["data"]:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            continue
        model_id = item["id"]
        label = f"{model_id} {item.get('name', '')}".lower()
        if not model_id or any(
            word in label
            for word in ("thinking", "reasoning", "embed", "rerank", "whisper", "transcrib")
        ):
            continue
        try:
            if "text" not in item.get("input_modalities", []):
                continue
            if "text" not in item.get("output_modalities", []):
                continue
            prices = item["price"]
            input_price = Decimal(str(prices["input"]["usd"]))
            output_price = Decimal(str(prices["output"]["usd"]))
            if input_price > 1 or output_price > 3:
                continue
        except (KeyError, TypeError, ValueError, ArithmeticError):
            continue
        if not input_price.is_finite() or not output_price.is_finite():
            continue
        if input_price < 0 or output_price < 0:
            continue
        choices.append((input_price + output_price, model_id))
    return min(choices)[1] if choices else None


async def _run_live_benchmark(
    tmp_path: Path, *, provider: str, model: str, parameters: dict, secret: str | None = None
):
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
    summary = next(item for item in result.candidate_summaries if item.id == "live-smoke")
    assert summary.total_input_tokens == (usage["input_tokens"] or 0)
    assert summary.total_output_tokens == (usage["output_tokens"] or 0)

    persisted_result = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
    assert result.status == persisted_result["status"] == "completed"
    assert persisted_result["candidate_summaries"][0]["provider_success_count"] == 1
    persisted_summary = persisted_result["candidate_summaries"][0]
    assert persisted_summary["total_input_tokens"] == summary.total_input_tokens
    assert persisted_summary["total_output_tokens"] == summary.total_output_tokens
    if secret:
        for path in run_dir.iterdir():
            assert secret not in path.read_text(encoding="utf-8")


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


@pytest.mark.parametrize(
    "provider,catalog,expected",
    [
        (
            "chutes",
            {
                "data": [
                    {
                        "id": "image-only",
                        "input_modalities": ["image"],
                        "output_modalities": ["text"],
                        "price": {"input": {"usd": 0.01}, "output": {"usd": 0.01}},
                    },
                    {
                        "id": "native/text",
                        "input_modalities": ["text"],
                        "output_modalities": ["text"],
                        "price": {"input": {"usd": 0.1}, "output": {"usd": 0.3}},
                    },
                ]
            },
            "native/text",
        ),
        (
            "nosana",
            {
                "data": [
                    {
                        "id": "not-serving",
                        "available": False,
                        "pricing": {"prompt": "0.000000001", "completion": "0.000000001"},
                    },
                    {
                        "id": "native/embed-model",
                        "available": True,
                        "pricing": {"prompt": "0.000000001", "completion": "0.000000001"},
                    },
                    {
                        "id": "current/text",
                        "available": True,
                        "pricing": {"prompt": "0.0000001", "completion": "0.0000003"},
                    },
                ]
            },
            None,
        ),
        ("chutes", {"data": [{"id": "only-image", "input_modalities": ["image"]}]}, None),
        ("nosana", {"data": [{"id": "offline", "available": False}]}, None),
        ("nosana", {"data": "malformed"}, None),
    ],
)
def test_live_catalog_selection_is_conservative(provider, catalog, expected):
    assert _select_live_model(provider, catalog) == expected


def test_live_catalog_selection_uses_override_without_catalog():
    assert _select_live_model("chutes", {}, override="native/explicit") == "native/explicit"


def test_nosana_live_override_must_be_currently_served():
    catalog = {
        "data": [
            {"id": "native/chat", "available": True},
            {"id": "native/offline", "available": False},
        ]
    }
    assert _select_live_model("nosana", catalog, override="native/chat") == "native/chat"
    assert _select_live_model("nosana", catalog, override="native/offline") is None
    assert _select_live_model("nosana", catalog, override="not-listed") is None
    assert _select_live_model("nosana", {"data": "malformed"}, override="native/chat") is None


@pytest.mark.provider_live
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider,key_name,model_name,base_url",
    [
        ("chutes", "CHUTES_API_KEY", "CHUTES_TEST_MODEL", "https://llm.chutes.ai/v1"),
        ("morpheus", "MORPHEUS_API_KEY", "MORPHEUS_TEST_MODEL", "https://api.mor.org/api/v1"),
        ("nosana", "NOSANA_API_KEY", "NOSANA_TEST_MODEL", "https://inference.nosana.com/v1"),
    ],
)
async def test_decentralized_provider_live_benchmark(
    tmp_path, provider, key_name, model_name, base_url
):
    key = os.environ.get(key_name)
    if not key:
        pytest.skip(f"{key_name} is not set")
    model = os.environ.get(model_name)
    if not model and provider in {"morpheus", "nosana"}:
        pytest.skip(f"{model_name} is required for a conservative live check")
    if provider == "nosana" or not model:
        headers = {"Authorization": f"Bearer {key}"} if provider == "nosana" else {}
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(base_url + "/models", headers=headers)
            response.raise_for_status()
        model = _select_live_model(provider, response.json(), override=model)
    if not model:
        pytest.skip(f"no suitable current {provider} text model in catalog")
    print(f"{provider} live model: {model}")
    await _run_live_benchmark(
        tmp_path, provider=provider, model=model, parameters={"max_tokens": 32}, secret=key
    )
