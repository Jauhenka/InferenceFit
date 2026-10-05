"""Named decentralized gateway profiles through the existing public benchmark path."""

import json
import secrets

import httpx
import pytest

from inferencefit import benchmark
from inferencefit.contracts import CandidateSpec
from inferencefit.contracts import TestCase as Case
from inferencefit.credentials import EnvironmentCredentialResolver
from inferencefit.errors import MissingCredentialError
from inferencefit.providers import OpenAICompatibleProvider, create_provider

PROFILES = [
    ("chutes", "https://llm.chutes.ai/v1", "CHUTES_API_KEY"),
    ("morpheus", "https://api.mor.org/api/v1", "MORPHEUS_API_KEY"),
    ("nosana", "https://inference.nosana.com/v1", "NOSANA_API_KEY"),
]


@pytest.mark.parametrize("provider,base_url,key_name", PROFILES)
async def test_named_profile_uses_shared_adapter_and_fallback(
    provider, base_url, key_name, tmp_path, monkeypatch, respx_mock
):
    monkeypatch.setenv(key_name, "fallback-token")
    route = respx_mock.post(base_url + "/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "model": "served/native-id",
                "choices": [{"message": {"content": "OK"}}],
                "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
            },
        )
    )
    candidate = CandidateSpec(id="profile", provider=provider, model="native/model:id")
    adapter = create_provider(
        candidate, spec_dir=tmp_path, resolver=EnvironmentCredentialResolver()
    )
    assert type(adapter) is OpenAICompatibleProvider
    response = await adapter.complete(
        candidate,
        Case.model_validate(
            {"id": "c", "request": {"messages": [{"role": "user", "content": "hi"}]}}
        ),
        0,
    )
    assert (response.provider, response.model, response.raw_output) == (
        provider,
        "served/native-id",
        "OK",
    )
    assert (response.input_tokens, response.output_tokens, response.total_tokens) == (2, 3, 5)
    request = route.calls[0].request
    assert request.headers["Authorization"] == "Bearer fallback-token"
    assert json.loads(request.content)["model"] == "native/model:id"
    assert "stream" not in json.loads(request.content)


@pytest.mark.parametrize("provider,base_url,key_name", PROFILES)
async def test_credential_ref_precedes_fallback_and_base_url_override(
    provider, base_url, key_name, tmp_path, monkeypatch, respx_mock
):
    monkeypatch.setenv(key_name, "fallback-token")
    monkeypatch.setenv("INFERENCEFIT_CREDENTIAL_NAMED", "reference-token")
    route = respx_mock.post("https://override.example.test/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]})
    )
    candidate = CandidateSpec(
        id="profile",
        provider=provider,
        model="opaque/model",
        credential_ref="named",
        base_url="https://override.example.test/v1",
    )
    adapter = create_provider(
        candidate, spec_dir=tmp_path, resolver=EnvironmentCredentialResolver()
    )
    assert type(adapter) is OpenAICompatibleProvider
    await adapter.complete(
        candidate,
        Case.model_validate(
            {"id": "c", "request": {"messages": [{"role": "user", "content": "hi"}]}}
        ),
        0,
    )
    assert route.calls[0].request.headers["Authorization"] == "Bearer reference-token"


@pytest.mark.parametrize("provider,base_url,key_name", PROFILES)
def test_named_profile_missing_key_fails_without_secret(
    provider, base_url, key_name, tmp_path, monkeypatch
):
    monkeypatch.delenv(key_name, raising=False)
    candidate = CandidateSpec(id="profile", provider=provider, model="m")
    with pytest.raises(MissingCredentialError) as caught:
        create_provider(candidate, spec_dir=tmp_path, resolver=EnvironmentCredentialResolver())
    assert key_name in str(caught.value)
    assert base_url not in str(caught.value)


@pytest.mark.parametrize("provider,base_url,key_name", PROFILES)
@pytest.mark.parametrize("configured_pricing", [False, True])
async def test_named_provider_public_benchmark_preserves_identity_cost_and_secret_safety(
    provider, base_url, key_name, configured_pricing, tmp_path, monkeypatch, respx_mock, caplog
):
    secret = "secret-" + secrets.token_hex(16)
    monkeypatch.setenv(key_name, secret)
    (tmp_path / "dataset.jsonl").write_text(
        json.dumps({"id": "c", "request": {"messages": [{"role": "user", "content": "OK?"}]}})
        + "\n",
        encoding="utf-8",
    )
    candidate = {"id": "profile", "provider": provider, "model": "native/model"}
    if configured_pricing:
        candidate["pricing"] = {"input_per_million": 2, "output_per_million": 4}
    spec = {
        "schema_version": "0.1",
        "dataset": {"path": "dataset.jsonl"},
        "candidates": [candidate],
        "execution": {"retry": {"max_attempts": 1}},
    }
    spec_path = tmp_path / "eval.yaml"
    import yaml

    spec_path.write_text(yaml.safe_dump(spec), encoding="utf-8")
    route = respx_mock.post(base_url + "/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "model": "served/native",
                "choices": [{"message": {"content": "OK"}}],
                "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
            },
        )
    )
    result = await benchmark(spec_path, output_root=tmp_path / "runs")
    run_dir = tmp_path / "runs" / result.run_id
    row = json.loads((run_dir / "observations.jsonl").read_text(encoding="utf-8"))
    assert result.status == "completed"
    assert (row["provider_status"], row["provider"], row["model"], row["raw_output"]) == (
        "success",
        provider,
        "served/native",
        "OK",
    )
    assert row["usage"] == {"input_tokens": 2, "output_tokens": 3, "total_tokens": 5}
    assert row["cost_source"] == ("configured_pricing" if configured_pricing else None)
    assert row["cost_usd"] == (16 / 1_000_000 if configured_pricing else None)
    assert route.calls[0].request.headers["Authorization"] == f"Bearer {secret}"
    assert secret not in caplog.text
    for path in run_dir.iterdir():
        assert secret not in path.read_text(encoding="utf-8")
