"""Shared benchmark orchestration for Python, CLI, and HTTP."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import secrets
from datetime import UTC, datetime
from pathlib import Path

from inferencefit.contracts import CandidateSpec, ResultBundle, RoutingPolicy
from inferencefit.credentials import EnvironmentCredentialResolver
from inferencefit.dataset import load_jsonl_dataset
from inferencefit.execution import run_evaluations
from inferencefit.execution.budget import BudgetController
from inferencefit.metrics import aggregate_candidate
from inferencefit.optimization import (
    apply_constraints,
    pareto_frontier,
    rank_summaries,
    simulate_cascade,
)
from inferencefit.providers import create_provider
from inferencefit.reporting import render_markdown
from inferencefit.spec import load_evaluation_spec
from inferencefit.storage import FilesystemArtifactStore

logger = logging.getLogger(__name__)


def _hash(value) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def new_run_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(3)


def _resume_invocation_namespace(manifest: dict, candidates: list[CandidateSpec]) -> str:
    namespace = manifest.get("invocation_namespace")
    if isinstance(namespace, str) and namespace:
        return namespace
    if any(candidate.provider == "inferencefit-cloud" for candidate in candidates):
        raise ValueError("Cloud resume requires the original invocation namespace")
    return secrets.token_hex(16)


async def benchmark(
    spec_path: str | Path,
    *,
    resume: str | None = None,
    output_root: str | Path = ".inferencefit/runs",
    run_id: str | None = None,
    budget: BudgetController | None = None,
) -> ResultBundle:
    # The public package imports core before publishing its version.
    from inferencefit import __version__

    if budget is not None and resume is not None:
        raise ValueError("Budget-controlled runs do not support resume")

    loaded = load_evaluation_spec(spec_path)
    spec = loaded.spec
    dataset = load_jsonl_dataset(loaded.resolve_dataset_path())
    logger.info("dataset loaded", extra={"case_count": len(dataset)})
    spec_dump = spec.model_dump(mode="json", exclude_none=True)
    spec_hash = _hash(spec_dump)
    store = FilesystemArtifactStore(Path(output_root))
    started = datetime.now(UTC)

    resolver = EnvironmentCredentialResolver()
    providers = {
        candidate.id: create_provider(
            candidate, spec_dir=loaded.source_path.parent, resolver=resolver
        )
        for candidate in spec.candidates
    }

    if resume:
        active_run_id = resume
        run_dir = store.run_dir(active_run_id)
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        if manifest["spec_hash"] != spec_hash or manifest["dataset_hash"] != dataset.sha256:
            raise ValueError("resume spec or dataset is incompatible with the existing run")
        existing = store.observations(active_run_id)
        started = datetime.fromisoformat(manifest["started_at"])
        invocation_namespace = _resume_invocation_namespace(manifest, spec.candidates)
    else:
        active_run_id = run_id or new_run_id()
        invocation_namespace = secrets.token_hex(16)
        run_dir = store.create(active_run_id)
        existing = []
        store.atomic_yaml(
            run_dir / "spec.yaml",
            spec.model_dump(
                mode="json",
                exclude_none=True,
                exclude={"candidates": {"__all__": {"credential_ref"}}},
            ),
        )
        (run_dir / "dataset.jsonl").write_text(
            loaded.resolve_dataset_path().read_text(encoding="utf-8"), encoding="utf-8"
        )

    manifest = {
        "schema_version": "0.1",
        "inferencefit_version": __version__,
        "run_id": active_run_id,
        "invocation_namespace": invocation_namespace,
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
            spec,
            list(dataset),
            provider_factory,
            store,
            active_run_id,
            existing=existing,
            invocation_namespace=invocation_namespace,
            budget=budget,
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
    if budget is not None and (budget.stopped or budget.failed or budget.uncertain):
        ranking = []
    recommendation = ranking[0].id if ranking else None
    if recommendation is None:
        if budget is not None and budget.stopped:
            reason = "Budget exhausted before all planned requests completed."
        elif budget is not None and (budget.failed or budget.uncertain):
            reason = "Provider failures or uncertain costs prevent a demo recommendation."
        else:
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
        status="failed" if budget is not None and budget.stopped else "completed",
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
        status="incomplete" if budget is not None and budget.stopped else "completed",
        completed_at=result.completed_at.isoformat(),
        planned_observations=len(dataset) * len(spec.candidates) * spec.execution.repetitions,
    )
    if budget is not None:
        manifest["budget"] = {
            "limit_usd": budget.limit_usd,
            "reported_or_estimated_usd": budget.known_usd,
            "uncertain_reservation_usd": budget.uncertain_usd,
            "completed_requests": budget.completed,
            "failed_requests": budget.failed,
            "uncertain_requests": budget.uncertain,
            "budget_exhausted": budget.stopped,
        }
    store.atomic_json(run_dir / "manifest.json", manifest)
    logger.info("run completed", extra={"run_id": active_run_id})
    return result
