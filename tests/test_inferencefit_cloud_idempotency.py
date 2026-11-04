"""Run-scoped invocation identity for billable adapters."""

from __future__ import annotations

import json

import pytest

from inferencefit import benchmark
from inferencefit.contracts import CandidateSpec, EvaluationSpec, TestCase
from inferencefit.core import _hash
from inferencefit.dataset import load_jsonl_dataset
from inferencefit.execution.runner import run_evaluations
from inferencefit.providers import ProviderError, ProviderResponse
from inferencefit.spec import load_evaluation_spec
from inferencefit.storage import FilesystemArtifactStore


class InvocationAwareFake:
    def __init__(self):
        self.identities = []

    async def complete(self, candidate, case, repetition):
        raise AssertionError("runner should use invocation-aware capability")

    async def complete_with_invocation(self, candidate, case, repetition, invocation_id):
        self.identities.append(invocation_id)
        if len(self.identities) == 1:
            raise ProviderError("transient", retryable=True, kind="network")
        return ProviderResponse(raw_output="ok", latency_ms=1, cost_usd=0.0002)


@pytest.mark.asyncio
async def test_retry_reuses_same_invocation_identity(tmp_path):
    provider = InvocationAwareFake()
    candidate = CandidateSpec(id="cloud", provider="inferencefit-cloud", model="catalog-id")
    spec = EvaluationSpec(
        dataset={"path": "unused.jsonl"},
        candidates=[candidate],
        execution={"retry": {"max_attempts": 2, "initial_backoff_ms": 0, "max_backoff_ms": 0}},
    )
    case = TestCase(id="case", request={"messages": [{"role": "user", "content": "hello"}]})
    store = FilesystemArtifactStore(tmp_path)
    store.create("run")
    observations = await run_evaluations(
        spec, [case], lambda _: provider, store, "run", invocation_namespace="namespace-one"
    )
    assert len(provider.identities) == 2
    assert provider.identities[0] == provider.identities[1]
    assert len(provider.identities[0]) <= 128
    assert observations[0].provider_attempts == 2
    assert observations[0].cost_usd == pytest.approx(0.0002)


@pytest.mark.asyncio
async def test_repetitions_and_namespaces_have_distinct_identities(tmp_path):
    candidate = CandidateSpec(id="cloud", provider="inferencefit-cloud", model="catalog-id")
    spec = EvaluationSpec(
        dataset={"path": "unused.jsonl"},
        candidates=[candidate],
        execution={"repetitions": 2, "retry": {"max_attempts": 1}},
    )
    case = TestCase(id="case", request={"messages": [{"role": "user", "content": "hello"}]})

    class CapturingProvider:
        def __init__(self):
            self.identities = []

        async def complete_with_invocation(self, candidate, case, repetition, invocation_id):
            self.identities.append(invocation_id)
            return ProviderResponse(raw_output="ok", latency_ms=1)

    first, second = CapturingProvider(), CapturingProvider()
    for name, provider, namespace in (
        ("one", first, "namespace-one"),
        ("two", second, "namespace-two"),
    ):
        store = FilesystemArtifactStore(tmp_path / name)
        store.create("same-human-run-id")
        await run_evaluations(
            spec,
            [case],
            lambda _, provider=provider: provider,
            store,
            "same-human-run-id",
            invocation_namespace=namespace,
        )
    assert len(set(first.identities)) == 2
    assert set(first.identities).isdisjoint(second.identities)


@pytest.mark.asyncio
async def test_manifest_namespace_is_random_across_runs_and_stable_on_resume(tmp_path):
    (tmp_path / "dataset.jsonl").write_text(
        json.dumps({"id": "c", "request": {"messages": [{"role": "user", "content": "x"}]}}) + "\n",
        encoding="utf-8",
    )
    spec_path = tmp_path / "eval.yaml"
    spec_path.write_text(
        """schema_version: '0.1'
dataset: {path: dataset.jsonl}
candidates:
  - {id: fixture, provider: fixture, model: sample}
""",
        encoding="utf-8",
    )
    for root in (tmp_path / "first", tmp_path / "second"):
        await benchmark(spec_path, output_root=root, run_id="same-human-run-id")
    first_manifest = tmp_path / "first/same-human-run-id/manifest.json"
    second_manifest = tmp_path / "second/same-human-run-id/manifest.json"
    first = json.loads(first_manifest.read_text(encoding="utf-8"))
    second = json.loads(second_manifest.read_text(encoding="utf-8"))
    assert first["invocation_namespace"] != second["invocation_namespace"]
    await benchmark(spec_path, output_root=tmp_path / "first", resume="same-human-run-id")
    resumed = json.loads(first_manifest.read_text(encoding="utf-8"))
    assert resumed["invocation_namespace"] == first["invocation_namespace"]


@pytest.mark.asyncio
async def test_cloud_resume_without_invocation_namespace_fails_closed(tmp_path, monkeypatch):
    (tmp_path / "dataset.jsonl").write_text(
        json.dumps({"id": "c", "request": {"messages": [{"role": "user", "content": "x"}]}}) + "\n",
        encoding="utf-8",
    )
    spec_path = tmp_path / "eval.yaml"
    spec_path.write_text(
        """schema_version: '0.1'
dataset: {path: dataset.jsonl}
candidates:
  - {id: cloud, provider: inferencefit-cloud, model: catalog-id}
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("INFERENCEFIT_CLOUD_TOKEN", "test-secret")
    monkeypatch.setenv("INFERENCEFIT_CLOUD_API_URL", "http://127.0.0.1:8765")
    run_dir = tmp_path / "runs" / "existing"
    run_dir.mkdir(parents=True)
    manifest = {
        "spec_hash": _hash(
            load_evaluation_spec(spec_path).spec.model_dump(mode="json", exclude_none=True)
        ),
        "dataset_hash": load_jsonl_dataset(tmp_path / "dataset.jsonl").sha256,
        "started_at": "2026-10-12T00:00:00+00:00",
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="invocation namespace"):
        await benchmark(spec_path, output_root=tmp_path / "runs", resume="existing")
