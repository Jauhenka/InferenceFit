# OpenRouter 0.2.0 Design

## Intent and success criteria

InferenceFit 0.2.0 makes OpenRouter a first-class inference provider through the existing
benchmark path. A candidate using `provider: openrouter` and a native OpenRouter model ID must use
the documented chat-completions endpoint, resolve `OPEN_ROUTER_API_KEY`, preserve the existing
retry/timeout behavior, persist authoritative usage and cost metadata when OpenRouter returns it,
and remain interchangeable with Fireworks, DeepSeek, fixture, and custom OpenAI-compatible
candidates.

The implementation must not add OpenRouter routing policy, fallbacks, provider selection, cloud
billing, UI, or other unrelated features. Unit tests remain offline. Live checks are explicit and
skip when credentials are absent.

## Chosen architecture

Keep the existing `OpenAICompatibleProvider` as the shared HTTP transport and response-text/token
normalizer. Add a small `OpenRouterProvider` specialization rather than teaching the benchmark
engine about OpenRouter. The shared adapter gains narrow extension points for request headers,
response metadata, and normalized HTTP errors; the OpenRouter specialization opts into
`X-OpenRouter-Metadata: enabled` and extracts the selected upstream backend from the returned
metadata.

Extend `ProviderResponse` and `Observation` only with optional normalized fields: total tokens,
actual model, provider/backend, provider-reported request cost, and cost provenance. Existing
serialized observations continue to validate because every new field is optional or defaulted.
The runner gives authoritative provider-reported cost precedence over candidate pricing; when it
falls back to configured per-million-token pricing, it records that provenance explicitly.

This is preferred over two alternatives:

1. Putting OpenRouter branches directly in the benchmark engine would couple orchestration to a
   vendor and violate the provider boundary.
2. Treating OpenRouter only as another URL preset would leave its credential, cost, routing
   metadata, error semantics, live verification, and documentation below first-class support.

## Request and response flow

1. Configuration keeps native model IDs such as `openrouter/free` or `provider/model-name`.
2. Core provider construction resolves `OPEN_ROUTER_API_KEY` and selects `OpenRouterProvider` only
   for `provider: openrouter`; other non-fixture candidates retain the generic adapter.
3. The adapter posts the existing messages and candidate parameters to
   `https://openrouter.ai/api/v1/chat/completions` with Bearer authentication and OpenRouter
   metadata opt-in. Parameters such as `temperature`, `max_tokens`, and
   `max_completion_tokens` pass through without claiming universal model support.
4. The adapter normalizes response text, prompt/completion/total tokens, actual model,
   provider-reported `usage.cost`, and the selected upstream provider when present. Missing
   optional metadata leaves fields unset and never turns a successful completion into an error.
5. The existing runner owns retry timing and overall timeout. It persists normalized fields and
   selects provider-reported cost before configured pricing.

## Error and secret handling

HTTP authentication/authorization failures are non-retryable authentication errors. Rate limits,
request-timeout statuses, network timeouts, and server/provider availability failures are
retryable; other client errors are non-retryable HTTP errors. Error messages contain normalized
status information, never response bodies, request headers, or credentials.

Missing `OPEN_ROUTER_API_KEY` fails during credential resolution with an error that names only the
environment variable checked. Credentials remain excluded from specs, manifests, observations,
logs, fixtures, and test output.

## Tests and live validation

Offline tests cover request construction, native model IDs, text and usage normalization,
provider-reported cost precedence and provenance, selected-backend extraction, missing optional
fields, missing credentials, authentication failure, rate limiting, general HTTP failure,
timeout/network failure, malformed responses, retries, and secret redaction. Existing generic,
Fireworks, DeepSeek, fixture, artifact, CLI, and packaging tests must stay green.

An opt-in live pytest uses `OPEN_ROUTER_API_KEY`, allows `OPEN_ROUTER_TEST_MODEL`, defaults to the
documented free text router `openrouter/free`, and runs a tiny deterministic prompt through the
normal `benchmark()` path. It validates a real completion plus the persisted observation/result
pipeline and skips cleanly without the key. A concise example spec and README command expose the
same path to users.

## Version and documentation

The package, API health/version reporting, run manifests, CI package checks, release metadata
tests, README, and changelog move consistently to `0.2.0`. Serialized contract schema versions
remain `0.1`; this release adds backward-compatible optional fields rather than inventing a new
schema version without a migration need.

The README lists OpenRouter with the exact environment variable `OPEN_ROUTER_API_KEY`, a minimal
candidate example, a native model ID, and the live-test command. It states that parameter support
varies by model and that provider-reported cost is used when available.

