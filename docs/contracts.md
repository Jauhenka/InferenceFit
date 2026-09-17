# Serialized contracts

EvaluationSpec, TestCase, Observation, ResultBundle, and RoutingPolicy are language-neutral public formats with `schema_version: "0.1"` where serialized. They contain only JSON/YAML primitives and explicit field names, so a future non-Python SDK need not deserialize Python objects or recompute rankings.

JSON Pointer fields follow RFC 6901, including `~0` and `~1` escaping. Dataset hashing uses canonical JSON with sorted keys and compact separators, one newline-delimited record at a time. Nearest-rank percentiles use `ceil(p * n)` with a minimum rank of one.

`validation_pass_rate` is passes divided by provider-successful responses. `end_to_end_success_rate` is passes divided by all planned evaluations, so provider errors reduce it. `min_success_rate` always uses end-to-end success.

Pareto dominance requires one configuration to be no worse on every known shared dimension and strictly better on at least one: validation/end-to-end quality and provider reliability are maximized; cost and p95 latency are minimized. Unknown values are never coerced to zero.

Balanced-v1 uses fixed weights documented in the README. Equal cost or latency values receive a normalized score of 1.0. Ties then prefer higher end-to-end success, lower known cost, lower p95 latency, and lexicographically smaller ID.

RoutingPolicy is `single`, `fallback`, or explicit `none`. Only runtime-capable validator IDs can appear under fallback triggers. Evaluation-only failures never cause runtime fallback.

Local Python validators use the explicit signature `validate_answer(test_case: TestCase, response: CandidateResponse) -> ValidationResult | bool`. `CandidateResponse` exposes `raw_output` and best-effort `parsed_output`. The callable runs locally with the current process permissions and is not sandboxed.
