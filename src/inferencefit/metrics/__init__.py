"""Pure aggregation and deterministic percentile functions."""

from __future__ import annotations

import math
from statistics import fmean

from inferencefit.contracts import CandidateSummary, Observation


def nearest_rank(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(percentile * len(ordered)))
    return ordered[rank - 1]


def aggregate_candidate(candidate_id: str, observations: list[Observation]) -> CandidateSummary:
    planned = len(observations)
    successes = [item for item in observations if item.provider_status == "success"]
    passed = [item for item in successes if item.validation and item.validation.passed]
    latencies = [item.latency_ms for item in observations if item.latency_ms is not None]
    costs = [item.cost_usd for item in observations if item.cost_usd is not None]
    costs_known = len(costs) == planned if planned else False
    total_cost = sum(costs) if costs_known else None
    return CandidateSummary(
        id=candidate_id,
        planned_count=planned,
        provider_success_count=len(successes),
        provider_error_count=planned - len(successes),
        provider_success_rate=len(successes) / planned if planned else 0,
        provider_error_rate=(planned - len(successes)) / planned if planned else 0,
        validation_pass_count=len(passed),
        validation_pass_rate=len(passed) / len(successes) if successes else 0,
        end_to_end_success_rate=len(passed) / planned if planned else 0,
        mean_latency_ms=fmean(latencies) if latencies else None,
        p50_latency_ms=nearest_rank(latencies, 0.5),
        p95_latency_ms=nearest_rank(latencies, 0.95),
        total_cost_usd=total_cost,
        mean_cost_per_request_usd=total_cost / planned
        if total_cost is not None and planned
        else None,
        cost_per_1k_requests_usd=total_cost / planned * 1000
        if total_cost is not None and planned
        else None,
        total_input_tokens=sum(item.usage.input_tokens or 0 for item in observations),
        total_output_tokens=sum(item.usage.output_tokens or 0 for item in observations),
    )


__all__ = ["aggregate_candidate", "nearest_rank"]
