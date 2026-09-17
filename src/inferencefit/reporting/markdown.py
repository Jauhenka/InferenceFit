from __future__ import annotations

from inferencefit.contracts import ResultBundle


def render_markdown(result: ResultBundle) -> str:
    summaries = [*result.candidate_summaries, *result.cascade_summaries]
    rows = [
        "| Configuration | E2E success | Provider errors | p95 ms | Cost/1k USD | Eligible |",
        "|---|---:|---:|---:|---:|:---:|",
    ]
    for item in summaries:
        cost = (
            "unknown"
            if item.cost_per_1k_requests_usd is None
            else f"{item.cost_per_1k_requests_usd:.6f}"
        )
        latency = "unknown" if item.p95_latency_ms is None else f"{item.p95_latency_ms:.1f}"
        row = (
            f"| {item.id} | {item.end_to_end_success_rate:.3f} | "
            f"{item.provider_error_rate:.3f} | {latency} | {cost} | {item.eligible} |"
        )
        rows.append(row)
    return "\n".join(
        [
            "# InferenceFit benchmark",
            "",
            f"- Run: `{result.run_id}`",
            f"- Objective: `{result.objective}`",
            f"- Recommendation: `{result.recommendation}`",
            f"- Reason: {result.recommendation_reason}",
            "",
            "## Comparison",
            "",
            *rows,
            "",
            "## Pareto frontier",
            "",
            ", ".join(f"`{x}`" for x in result.pareto_frontier) or "None",
            "",
            "## Artifacts",
            "",
            "`manifest.json`, `spec.yaml`, `dataset.jsonl`, `observations.jsonl`, "
            "`result.json`, `summary.md`, `routing-policy.yaml`",
            "",
        ]
    )
