"""Hard constraints, Pareto analysis, and deterministic ranking."""

from __future__ import annotations

from inferencefit.contracts import (
    CandidateSummary,
    ConstraintResult,
    Observation,
    TokenUsage,
    ValidatorSpec,
)
from inferencefit.metrics import aggregate_candidate

_METRICS = {
    "min_success_rate": ("end_to_end_success_rate", ">="),
    "max_p95_latency_ms": ("p95_latency_ms", "<="),
    "max_provider_error_rate": ("provider_error_rate", "<="),
    "max_error_rate": ("provider_error_rate", "<="),
    "max_cost_per_1k_requests_usd": ("cost_per_1k_requests_usd", "<="),
    "max_cost_usd": ("total_cost_usd", "<="),
}


def apply_constraints(summaries: list[CandidateSummary], constraints: dict[str, float]) -> None:
    for summary in summaries:
        results: list[ConstraintResult] = []
        for metric, required in constraints.items():
            attribute, comparison = _METRICS[metric]
            actual = getattr(summary, attribute)
            passed = actual is not None and (
                actual >= required if comparison == ">=" else actual <= required
            )
            results.append(
                ConstraintResult(
                    metric=metric,
                    passed=passed,
                    actual=actual,
                    required=required,
                    comparison=comparison,
                )
            )
        summary.constraint_results = results
        summary.failed_constraints = [item for item in results if not item.passed]
        summary.eligible = not summary.failed_constraints


def _dominates(left: CandidateSummary, right: CandidateSummary) -> bool:
    pairs = [
        (left.validation_pass_rate, right.validation_pass_rate, True),
        (left.end_to_end_success_rate, right.end_to_end_success_rate, True),
        (left.provider_success_rate, right.provider_success_rate, True),
        (left.cost_per_1k_requests_usd, right.cost_per_1k_requests_usd, False),
        (left.p95_latency_ms, right.p95_latency_ms, False),
    ]
    if any(a is None or b is None for a, b, _ in pairs):
        return False
    known = pairs
    no_worse = all(a >= b if high else a <= b for a, b, high in known)
    better = any(a > b if high else a < b for a, b, high in known)
    return no_worse and better


def pareto_frontier(summaries: list[CandidateSummary]) -> list[str]:
    return sorted(
        item.id
        for item in summaries
        if not any(_dominates(other, item) for other in summaries if other is not item)
    )


def rank_summaries(summaries: list[CandidateSummary], objective: str) -> list[CandidateSummary]:
    eligible = [item for item in summaries if item.eligible]
    if not eligible:
        return []
    if objective == "balanced":
        costs = [
            x.cost_per_1k_requests_usd for x in eligible if x.cost_per_1k_requests_usd is not None
        ]
        lats = [x.p95_latency_ms for x in eligible if x.p95_latency_ms is not None]
        for item in eligible:
            if item.cost_per_1k_requests_usd is None or item.p95_latency_ms is None:
                item.unrankable_reason = "balanced objective requires known cost and latency"
                continue
            c = (
                1.0
                if max(costs) == min(costs)
                else 1 - (item.cost_per_1k_requests_usd - min(costs)) / (max(costs) - min(costs))
            )
            lat = (
                1.0
                if max(lats) == min(lats)
                else 1 - (item.p95_latency_ms - min(lats)) / (max(lats) - min(lats))
            )
            item.objective_score = (
                0.45 * item.validation_pass_rate
                + 0.30 * c
                + 0.15 * lat
                + 0.10 * item.provider_success_rate
            )
        rankable = [x for x in eligible if x.objective_score is not None]
        return sorted(
            rankable, key=lambda x: (-x.objective_score, -x.end_to_end_success_rate, x.id)
        )
    attr, reverse = {
        "min_cost": ("cost_per_1k_requests_usd", False),
        "min_latency": ("p95_latency_ms", False),
        "max_quality": ("validation_pass_rate", True),
        "max_reliability": ("provider_success_rate", True),
    }[objective]
    rankable = []
    for item in eligible:
        value = getattr(item, attr)
        if value is None:
            item.unrankable_reason = f"{objective} requires known {attr}"
        else:
            item.objective_score = value
            rankable.append(item)
    sign = -1 if reverse else 1
    return sorted(
        rankable,
        key=lambda x: (
            sign * getattr(x, attr),
            -x.end_to_end_success_rate,
            x.cost_per_1k_requests_usd if x.cost_per_1k_requests_usd is not None else float("inf"),
            x.p95_latency_ms if x.p95_latency_ms is not None else float("inf"),
            x.id,
        ),
    )


def simulate_cascade(
    primary: str,
    fallback: str,
    observations: list[Observation],
    validators: list[ValidatorSpec],
) -> CandidateSummary:
    by_key = {(x.case_id, x.candidate_id, x.repetition): x for x in observations}
    primaries = [x for x in observations if x.candidate_id == primary]
    selected: list[Observation] = []
    fallback_count = 0
    gate_ids = {item.id for item in validators if item.routing_gate and item.runtime_capable}
    for first in primaries:
        gate_failed = bool(
            first.validation
            and any(
                not result.passed and result.validator_id in gate_ids
                for result in first.validation.results
            )
        )
        use_fallback = first.provider_status != "success" or gate_failed
        second = by_key.get((first.case_id, fallback, first.repetition)) if use_fallback else None
        chosen = second or first
        if use_fallback and second is not None:
            fallback_count += 1
        latency = None
        if first.latency_ms is not None and (second is None or second.latency_ms is not None):
            latency = first.latency_ms + (second.latency_ms if second else 0)
        selected.append(
            chosen.model_copy(
                update={
                    "candidate_id": f"cascade:{primary}->{fallback}",
                    "latency_ms": latency,
                    "cost_usd": None
                    if first.cost_usd is None or (second and second.cost_usd is None)
                    else (first.cost_usd or 0) + ((second.cost_usd or 0) if second else 0),
                    "usage": TokenUsage(
                        input_tokens=(first.usage.input_tokens or 0)
                        + ((second.usage.input_tokens or 0) if second else 0),
                        output_tokens=(first.usage.output_tokens or 0)
                        + ((second.usage.output_tokens or 0) if second else 0),
                    ),
                }
            )
        )
    summary = aggregate_candidate(f"cascade:{primary}->{fallback}", selected)
    summary.kind = "cascade"
    summary.primary = primary
    summary.fallback = fallback
    summary.fallback_rate = fallback_count / len(primaries) if primaries else 0
    return summary


__all__ = ["apply_constraints", "pareto_frontier", "rank_summaries", "simulate_cascade"]
