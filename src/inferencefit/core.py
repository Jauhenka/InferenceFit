"""Shared benchmark orchestration for Python, CLI, and HTTP."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import secrets
from datetime import UTC, datetime
from pathlib import Path

from inferencefit.contracts import ResultBundle, RoutingPolicy
from inferencefit.credentials import EnvironmentCredentialResolver
from inferencefit.dataset import load_jsonl_dataset
from inferencefit.execution import run_evaluations
from inferencefit.metrics import aggregate_candidate
from inferencefit.optimization import (
    apply_constraints,
    pareto_frontier,
    rank_summaries,
    simulate_cascade,
)
from inferencefit.providers import FixtureProvider, OpenAICompatibleProvider
from inferencefit.reporting import render_markdown
from inferencefit.spec import load_evaluation_spec
from inferencefit.storage import FilesystemArtifactStore

logger = logging.getLogger(__name__)


def _hash(value) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def new_run_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(3)


async def benchmark(
    spec_path: str | Path,
    *,
    resume: str | None = None,
    output_root: str | Path = ".inferencefit/runs",
    run_id: str | None = None,
) -> ResultBundle:
    loaded = load_evaluation_spec(spec_path)
    spec = loaded.spec
    dataset = load_jsonl_dataset(loaded.resolve_dataset_path())
    logger.info("dataset loaded", extra={"case_count": len(dataset)})
    spec_dump = spec.model_dump(mode="json", exclude_none=True)
    spec_hash = _hash(spec_dump)
    store = FilesystemArtifactStore(Path(output_root))
    started = datetime.now(UTC)

    resolver = EnvironmentCredentialResolver()
    providers = {}
    for candidate in spec.candidates:
        if candidate.provider == "fixture":
            providers[candidate.id] = FixtureProvider(loaded.source_path.parent)
        else:
            credential = resolver.resolve(candidate.credential_ref, candidate.provider)
            providers[candidate.id] = OpenAICompatibleProvider(credential)

    if resume:
        active_run_id = resume
        run_dir = store.run_dir(active_run_id)
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        if manifest["spec_hash"] != spec_hash or manifest["dataset_hash"] != dataset.sha256:
            raise ValueError("resume spec or dataset is incompatible with the existing run")
        existing = store.observations(active_run_id)
        started = datetime.fromisoformat(manifest["started_at"])
    else:
        active_run_id = run_id or new_run_id()
        run_dir = store.create(active_run_id)
        existing = []
        store.atomic_yaml(run_dir / "spec.yaml", spec_dump)
        (run_dir / "dataset.jsonl").write_text(
            loaded.resolve_dataset_path().read_text(encoding="utf-8"), encoding="utf-8"
        )

    manifest = {
        "schema_version": "0.1",
        "inferencefit_version": "0.1.0",
        "run_id": active_run_id,
        "started_at": started.isoformat(),
        "spec_hash": spec_hash,
        "dataset_hash": dataset.sha256,
        "status": "running",
        "candidates": [
            candidate.model_dump(mode="json", exclude={"credential_ref"})
            for candidate in spec.candidates
        ],
        "validators": [item.model_dump(mode="json") for item in spec.validators],
        "execution": spec.execution.model_dump(mode="json"),
    }
    store.atomic_json(run_dir / "manifest.json", manifest)
    logger.info("run started", extra={"run_id": active_run_id})

    def provider_factory(candidate):
        return providers[candidate.id]

    try:
        observations = await run_evaluations(
            spec, list(dataset), provider_factory, store, active_run_id, existing=existing
        )
    except asyncio.CancelledError:
        manifest.update(status="cancelled", completed_at=datetime.now(UTC).isoformat())
        store.atomic_json(run_dir / "manifest.json", manifest)
        raise
    except Exception:
        manifest.update(status="failed", completed_at=datetime.now(UTC).isoformat())
        store.atomic_json(run_dir / "manifest.json", manifest)
        raise
    candidate_summaries = [
        aggregate_candidate(
            candidate.id, [x for x in observations if x.candidate_id == candidate.id]
        )
        for candidate in spec.candidates
    ]
    cascade_summaries = []
    cascade = spec.optimization.cascade
    if cascade and cascade.fallbacks:
        cascade_summaries.append(
            simulate_cascade(cascade.primary, cascade.fallbacks[0], observations, spec.validators)
        )
    constraints = {item.metric: item.threshold for item in spec.constraints}
    all_summaries = [*candidate_summaries, *cascade_summaries]
    apply_constraints(all_summaries, constraints)
    ranking = rank_summaries(all_summaries, spec.optimization.objective)
    recommendation = ranking[0].id if ranking else None
    if recommendation is None:
        reason = "No configuration satisfied all constraints and objective requirements."
        policy = RoutingPolicy(strategy="none", reason=reason)
    else:
        chosen = ranking[0]
        reason = (
            f"Selected {recommendation} by deterministic {spec.optimization.objective} ranking."
        )
        if chosen.kind == "cascade":
            gates = [x.id for x in spec.validators if x.routing_gate and x.runtime_capable]
            policy = RoutingPolicy(
                strategy="fallback",
                primary=chosen.primary,
                fallback=chosen.fallback,
                fallback_on={"provider_error": True, "validator_failures": gates},
            )
        else:
            policy = RoutingPolicy(strategy="single", candidate=chosen.id)
    result = ResultBundle(
        run_id=active_run_id,
        started_at=started,
        provenance={"spec_hash": spec_hash, "dataset_hash": dataset.sha256},
        constraints=constraints,
        candidate_summaries=candidate_summaries,
        cascade_summaries=cascade_summaries,
        pareto_frontier=pareto_frontier(all_summaries),
        objective=spec.optimization.objective,
        formula_version="balanced-v1" if spec.optimization.objective == "balanced" else None,
        recommendation=recommendation,
        ranking=[x.id for x in ranking],
        recommendation_reason=reason,
        routing_policy=policy,
    )
    store.atomic_json(run_dir / "result.json", result.model_dump(mode="json"))
    store.atomic_yaml(
        run_dir / "routing-policy.yaml", policy.model_dump(mode="json", exclude_none=True)
    )
    store._atomic_text(run_dir / "summary.md", render_markdown(result))
    manifest.update(
        status="completed",
        completed_at=result.completed_at.isoformat(),
        planned_observations=len(observations),
    )
    store.atomic_json(run_dir / "manifest.json", manifest)
    logger.info("run completed", extra={"run_id": active_run_id})
    return result
