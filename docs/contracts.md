# Serialized contracts

EvaluationSpec, TestCase, Observation, ResultBundle, and RoutingPolicy are language-neutral public formats with `schema_version: "0.1"` where serialized. They contain only JSON/YAML primitives and explicit field names, so a future non-Python SDK need not deserialize Python objects or recompute rankings.

## Additive fields in 0.2.0

Package release 0.2.0 retains `schema_version: "0.1"`. `Observation` adds two optional,
nullable fields, each defaulting to `null` when absent in older observation records:

- `provider_backend`: the serving backend reported by OpenRouter, when available. This is
  separate from `provider` (the configured integration) and `model` (the response model ID).
- `cost_source`: `"provider_reported"` for a valid, non-negative finite request cost returned
  by the provider, or `"configured_pricing"` when cost is computed from the candidate's
  configured token prices. It is `null` when cost is unknown.

Provider-reported `cost_usd`, including zero, takes precedence over configured pricing.
Without a usable reported cost, estimation requires both input/output token counts and both
configured prices; missing data leaves `cost_usd` unknown. Invalid reported costs are ignored.
Missing or malformed token counts stay `null` in `usage`; a valid reported `total_tokens` can
be retained independently of the input/output counts. Aggregates retain unknown total cost
if any required observation cost is missing. Token totals sum known counts without inventing
missing usage.

Older schema 0.1 observations without the new fields load with the defaults and remain usable
for compatible resume operations. New readers accept both old and new records; older strict
readers may need updating to accept the additional keys. The existing candidate shape is
unchanged: `provider`, `model`, optional `base_url` and `credential_ref`, `parameters`, and
optional static `pricing`. No credentials appear in serialized contracts. Manifests report
the package's `inferencefit_version: "0.2.0"` separately from the serialized schema version.

## Evaluation and routing semantics

JSON Pointer fields follow RFC 6901, including `~0` and `~1` escaping. Dataset hashing uses canonical JSON with sorted keys and compact separators, one newline-delimited record at a time. Nearest-rank percentiles use `ceil(p * n)` with a minimum rank of one.

`validation_pass_rate` is passes divided by provider-successful responses. `end_to_end_success_rate` is passes divided by all planned evaluations, so provider errors reduce it. `min_success_rate` always uses end-to-end success.

Pareto dominance requires one configuration to be no worse on every known shared dimension and strictly better on at least one: validation/end-to-end quality and provider reliability are maximized; cost and p95 latency are minimized. Unknown values are never coerced to zero.

Balanced-v1 uses fixed weights documented in the README. Equal cost or latency values receive a normalized score of 1.0. Ties then prefer higher end-to-end success, lower known cost, lower p95 latency, and lexicographically smaller ID.

RoutingPolicy is `single`, `fallback`, or explicit `none`. Only runtime-capable validator IDs can appear under fallback triggers. Evaluation-only failures never cause runtime fallback.

Local Python validators use the explicit signature `validate_answer(test_case: TestCase, response: CandidateResponse) -> ValidationResult | bool`. `CandidateResponse` exposes `raw_output` and best-effort `parsed_output`. The callable runs locally with the current process permissions and is not sandboxed.
