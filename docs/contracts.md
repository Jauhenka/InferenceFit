# Serialized contracts

EvaluationSpec, TestCase, Observation, ResultBundle, and RoutingPolicy are language-neutral public formats with `schema_version: "0.1"` where serialized. They contain only JSON/YAML primitives and explicit field names, so a future non-Python SDK need not deserialize Python objects or recompute rankings.

## Additive fields in 0.2.0

Package release 0.2.0 retains `schema_version: "0.1"`. `Observation` adds five optional,
nullable keys, each defaulting to `null` when absent in older observation records:

- `provider`: the configured provider integration that produced the response.
- `model`: the actual response model ID reported by the provider, when available.
- `provider_backend`: the serving backend reported by OpenRouter, when available. This is
  separate from `provider` (the configured integration) and `model` (the response model ID).
- `cost_source`: `"provider_reported"` for a valid, non-negative finite request cost returned
  by the provider, or `"configured_pricing"` when cost is computed from the candidate's
  configured token prices. It is `null` when cost is unknown.
- `usage.total_tokens`: the provider-reported total token count, retained independently of the
  existing input and output token counts when available.

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
optional static `pricing`. No resolved credential values appear in serialized contracts. Manifests report
the package's `inferencefit_version: "0.2.0"` separately from the serialized schema version.

## Generic OpenAI-compatible candidates in 0.2.2

The serialized schema stays `"0.1"`. The canonical generic syntax is `provider: custom`, a
native `model`, and an explicit HTTP(S) API `base_url`, for example
`https://api.example.com/v1`. InferenceFit appends `/chat/completions`; a full completion URL is
invalid. `http://localhost:8000/v1`, `http://127.0.0.1:8000/v1`, and
`http://[::1]:8000/v1` are valid local bases. Remote endpoints should use HTTPS. A base URL
cannot contain userinfo, query, fragment, or whitespace. Its path must not carry secrets because
the URL is persisted in artifacts.

For Bearer authentication, `credential_ref: example-main` resolves through
`INFERENCEFIT_CREDENTIAL_EXAMPLE_MAIN`. Omit the reference for a credentialless local server.
The opaque reference is not a resolved credential; 0.2.2 preserves the existing spec/artifact
persistence behavior for that identifier. Resolved secret values must never appear in specs,
manifests, observations, results, logs, errors, or artifacts. No arbitrary environment-variable
name or custom HTTP header field is added.

`parameters` pass through to non-streaming chat completions except `model`, `messages`, and
`stream`, which are reserved and fail before HTTP. OpenAI-compatible services vary in supported
parameters and optional usage fields. Custom responses retain text, available token usage, the
actual returned model, and latency. The generic adapter does not interpret arbitrary response
cost metadata. Configured `pricing` can calculate cost when both token counts and prices exist;
otherwise cost is unknown, never zero by default.

Prefer a first-class adapter when available. An unknown provider name with explicit `base_url`
still routes through the generic adapter for backward compatibility, but this syntax is
deprecated and warns in 0.2.2. New configurations use `provider: custom`. Named-provider
`base_url` overrides still take precedence for 0.2.x compatibility and bypass provider-specific
behavior on that route.

## Named decentralized inference profiles in 0.2.3

`chutes`, `morpheus`, and `nosana` use the same `CandidateSpec` and non-streaming
`OpenAICompatibleProvider` as the generic chat route. Their respective default API bases are
`https://llm.chutes.ai/v1`, `https://api.mor.org/api/v1`, and
`https://inference.nosana.com/v1`. A normal candidate supplies its native `model` ID and no
`base_url`. The profile names are canonical lowercase identifiers; models remain opaque strings.
An explicit `base_url` override retains the named-provider compatibility behavior above.

Credential resolution checks an explicit opaque `credential_ref` first, then the named fallback:
`CHUTES_API_KEY`, `MORPHEUS_API_KEY`, or `NOSANA_API_KEY`. The resolved secret value never enters
the spec, manifest, observation, result, logs, errors, or artifacts. The existing persistence
contract for the opaque reference remains unchanged. Missing named-provider credentials fail
before a request. These profiles add no schema fields; serialized `schema_version: "0.1"`
continues unchanged.

Normal benchmarking does not query model catalogs. Chutes' public catalog and Nosana's
authenticated currently served catalog can assist an explicit model choice; Morpheus has an
authenticated active-model list. Availability and pricing change. The shared adapter normalizes
chat text, optional token usage, returned model, latency, and safe errors. It does not treat
catalog price or arbitrary response fields as authoritative request cost. User-configured
`pricing` and complete usage produce a calculated cost; otherwise cost is unknown. The shared
reserved `model`, `messages`, and `stream` parameter behavior still applies. Unknown names with
an explicit URL remain deprecated backward compatibility; new arbitrary endpoints use
`provider: custom`.

## Native Anthropic Messages in 0.2.4

`provider: anthropic` selects the native non-streaming Anthropic Messages adapter;
`provider: claude` is an alias for the same adapter. The serialized candidate still uses schema
version `"0.1"` and retains the authored provider spelling. Observations report canonical
`anthropic`.
Model IDs are opaque and never infer a provider. The optional `credential_ref` resolves before the
`ANTHROPIC_API_KEY` fallback; its existing persistence contract remains unchanged, while resolved
secret values are never serialized or logged. An explicit `base_url` retains the old generic
chat-completions override, so native Messages candidates omit it.

The adapter moves leading system messages to the top-level `system` field and preserves ordered
user/assistant text messages. Later system messages, named messages, and only-system cases fail
before HTTP. `model`, `messages`, `system`, and `stream` are reserved parameters. `max_tokens` is
required by the API and defaults to 1024 when omitted; `max_output_tokens` is an alias. No
temperature is added implicitly. Response text blocks, returned model, latency, and available
usage are normalized. Cached input counts are included in `usage.input_tokens` when reported.
Configured pricing can estimate cost with complete usage; it does not represent cache-specific
rates. Otherwise cost remains unknown. Errors use shared safe classification and bounded retries.

## Evaluation and routing semantics

JSON Pointer fields follow RFC 6901, including `~0` and `~1` escaping. Dataset hashing uses canonical JSON with sorted keys and compact separators, one newline-delimited record at a time. Nearest-rank percentiles use `ceil(p * n)` with a minimum rank of one.

`validation_pass_rate` is passes divided by provider-successful responses. `end_to_end_success_rate` is passes divided by all planned evaluations, so provider errors reduce it. `min_success_rate` always uses end-to-end success.

Pareto dominance requires one configuration to be no worse on every known shared dimension and strictly better on at least one: validation/end-to-end quality and provider reliability are maximized; cost and p95 latency are minimized. Unknown values are never coerced to zero.

Balanced-v1 uses fixed weights documented in the README. Equal cost or latency values receive a normalized score of 1.0. Ties then prefer higher end-to-end success, lower known cost, lower p95 latency, and lexicographically smaller ID.

RoutingPolicy is `single`, `fallback`, or explicit `none`. Only runtime-capable validator IDs can appear under fallback triggers. Evaluation-only failures never cause runtime fallback.

Local Python validators use the explicit signature `validate_answer(test_case: TestCase, response: CandidateResponse) -> ValidationResult | bool`. `CandidateResponse` exposes `raw_output` and best-effort `parsed_output`. The callable runs locally with the current process permissions and is not sandboxed.
