# Generic OpenAI-Compatible Provider 0.2.2 Design

## Intent and boundary

InferenceFit 0.2.2 makes an arbitrary OpenAI-compatible chat-completions endpoint a documented, tested candidate. The canonical public provider identifier is `custom`. It uses the existing `CandidateSpec`, `OpenAICompatibleProvider`, `benchmark()` runner, observations, artifacts, and CLI. There is one generic protocol family, not a plugin system or a second benchmark path.

The release succeeds when a user can validate and benchmark an endpoint supplied by their project, including an authenticated remote service or a credentialless local server, without a new branded adapter. A branded provider remains preferable when available: its adapter may normalize provider-specific request behavior, metadata, or cost that `custom` cannot.

## Post-0.2.1 behavior audit

| Question | Verified current behavior |
| --- | --- |
| Arbitrary `base_url`? | Yes. `CandidateSpec.base_url: str | None` accepts any string today; it has no URL validator (`src/inferencefit/contracts/candidates.py`). |
| Shared transport? | Yes. A truthy `base_url` makes `create_provider()` return `OpenAICompatibleProvider`, even for `openai` or `openrouter` (`src/inferencefit/providers/registry.py`). |
| Meaning of an arbitrary provider name? | It is carried into `ProviderResponse.provider` and thus the observation, but it selects no vendor behavior unless it matches a built-in. Unknown names fall back to the shared adapter; without an endpoint they fail only on the first request. A typo plus `base_url` therefore runs silently today. |
| Unknown-provider credentials? | `EnvironmentCredentialResolver.resolve(reference, provider)` has vendor fallbacks only for DeepSeek, Fireworks, Gemini, OpenAI, and OpenRouter. An unknown provider has no fallback (`src/inferencefit/credentials/__init__.py`). |
| Opaque `credential_ref`? | Yes. For example `example-main` maps to `INFERENCEFIT_CREDENTIAL_EXAMPLE_MAIN`; a missing explicitly referenced variable raises `MissingCredentialError`. Omitting the ref for an unknown/custom provider returns `None`. |
| Arbitrary environment variable? | No direct variable-name field exists. Users set the existing `INFERENCEFIT_CREDENTIAL_<NORMALIZED_REF>` variable, or copy a value into it in their shell or secret manager; no new resolver is needed. |
| Custom headers? | No candidate field accepts user headers. The adapter's internal `_request_headers` hook generates optional Bearer Authorization and lets the built-in OpenRouter subclass add its own metadata header; it does not take user configuration. |
| Candidate pricing? | Yes. `PricingSpec` accepts non-negative input/output prices per million tokens. The runner computes a cost only when both prices and both token counts exist (`src/inferencefit/execution/runner.py`). |
| Request parameters? | `parameters` is an arbitrary mapping splatted into the chat-completions JSON after `model` and `messages`; this currently permits overriding those two keys and sending `stream: true`, although the adapter only parses non-streaming JSON. Other optional fields pass through without translation (`OpenAICompatibleProvider.complete`). |
| Functionality versus UX gaps? | Generic dispatch, Bearer auth, credentialless calls, response text/usage/model, retry/timeout, normalized errors, configured pricing, and artifacts already exist. Missing work is explicit identity/URL validation, typo visibility, reserved-field hardening, focused end-to-end tests, and discoverable examples/docs/Skill guidance. |

Existing 0.2.0 design explicitly preserved custom endpoints and `base_url` precedence. Existing registry and provider tests pin those behaviors. The 0.2.1 Agent Skill and three preset projects use the same public validate/benchmark workflow; no new preset is needed.

## Public contract

The canonical example uses the existing schema without new fields:

```yaml
schema_version: "0.1"
dataset:
  path: cases.jsonl
candidates:
  - id: my-provider-model
    provider: custom
    model: some/model-name
    base_url: https://api.example.com/v1
    credential_ref: example-main
    parameters:
      max_tokens: 64
    pricing:
      input_per_million: 1.0
      output_per_million: 2.0
```

The environment supplies `INFERENCEFIT_CREDENTIAL_EXAMPLE_MAIN`. The native model string remains unchanged. For a credentialless local endpoint, omit `credential_ref` and use an explicit URL such as `http://127.0.0.1:8000/v1` or `http://[::1]:8000/v1`; the request has no Authorization header. The candidate `id` distinguishes runs and summaries, while a canonical custom response records `provider: custom` and the actual returned model when present. No cosmetic provider-label field or alias is added.

`provider: custom` requires `base_url` during `CandidateSpec` validation. Every explicitly supplied base URL, including a legacy branded override, must be an absolute `http` or `https` URL with a hostname. Reject blank/whitespace/control characters, credentials in URL userinfo, query or fragment, malformed port, and a full `/chat/completions` request URL. The value is an API **base**: the shared adapter strips trailing `/` and appends `/chat/completions` exactly once. `/v1` is common but not mandatory; existing DeepSeek's root base demonstrates why. Recommend HTTPS for remote services; allow HTTP for local and private endpoints in local OSS execution. Never put a key in any URL component: the base URL is stored in run artifacts.

Keep `credential_ref` as the only generic secret input. Do not infer provider-specific environment-variable names or automatically discover keys. A missing explicit reference fails before the run; an omitted reference means credentialless operation. Resolved values exist only in adapter memory and the outgoing Bearer header. Preserve the existing `core.benchmark()` persistence behavior for opaque `credential_ref` identifiers; do not change artifacts solely to hide those identifiers. Tests must prove the **resolved secret value** is absent from specs, manifests, observations, results, logs, errors, and other artifacts. User-authored parameter values and base URL are persisted, so documentation must prohibit placing secrets there.

Defer custom headers. A plain `headers:` mapping would be serialized into artifacts, inviting secret leakage; secret-header references would need a second credential interface. 0.2.2 supports standard optional Bearer auth only. Gateways requiring other headers remain a documented limitation.

## Dispatch and compatibility

Formalize `custom` explicitly in the fixed registry, returning `OpenAICompatibleProvider` after the single existing resolver call. Keep existing named providers and URL presets: Fireworks, DeepSeek, OpenRouter, OpenAI, Gemini, Ollama, vLLM, and fixture. A named provider with explicit `base_url` keeps its 0.2.x precedence and uses the shared chat path, including `openai` and `openrouter`; document that this bypasses provider-specific behavior such as OpenRouter's cost/backend metadata and OpenAI's Responses API. This is a compatibility affordance, not the recommended syntax for a new endpoint.

Unknown provider names **with** `base_url` remain accepted for 0.2.x backward compatibility but are deprecated, not a second supported generic syntax. New configurations use `provider: custom`. `create_provider()` emits a visible, secret-safe `UserWarning` directing users to `custom`; the warning does not repeat user-controlled labels or URL text. The original label remains in legacy observations. Thus a misspelled name no longer silently looks supported. Unknown names **without** a URL retain today's request-time `ProviderError` to avoid an unrelated timing change. Do not add aliases or a generalized protocol registry. Tests pin the precedence, warning, provider identity, and unaffected branded dispatch.

## Request, response, error, and cost flow

`OpenAICompatibleProvider` keeps the existing non-streaming `POST <base>/chat/completions` request: native `model`, case messages, and supported `CandidateSpec.parameters`. Reject `parameters.model`, `parameters.messages`, and `parameters.stream` as reserved configuration errors before HTTP in the shared chat adapter. The first two cannot replace the declared model or benchmark case; the third cannot switch a non-streaming parser to a streaming response. This small hardening also applies to branded adapters using that transport. Optional parameters are otherwise passed through as today. OpenAI-compatible targets vary; unsupported parameters receive the target's ordinary HTTP error and no universal parameter compatibility is promised.

Continue extracting the first choice's string message content, optional non-negative integer prompt/completion/total token counts, optional returned model (falling back to requested model), and latency. Unknown optional usage or metadata must not fail successful text inference. Keep provider metadata limited to what the current adapter supports; do not treat arbitrary `usage.cost` or `provider` response fields as authoritative for `custom`.

The common error normalizer maps 401/403 to non-retryable auth/permission failures, 408/429/5xx to retryable timeout/rate/server failures, malformed JSON or completion shape to a non-retryable response error, and transport timeout/network failure to safe retryable errors. It never embeds response bodies, request headers, or exception text. The common runner retains the total timeout, bounded backoff, attempts, and terminal observation semantics. No vendor-specific error parser is added.

Cost precedence remains provider-reported request cost (including `0.0`) when an adapter already supplies it, otherwise configured token pricing when complete, otherwise `None`. The generic adapter currently supplies no provider-reported monetary cost, even if an arbitrary response includes a `usage.cost` field. A custom observation therefore has `configured_pricing` or unknown cost; unknown is not zero. Aggregated cost remains unknown when observations lack cost.

## UX, release, and security

Update README, `docs/contracts.md`, `examples/README.md`, a single hand-maintained generic example, CHANGELOG, new `docs/releases/0.2.2.md`, and current `docs/releasing.md` guidance. Document remote Bearer and credentialless localhost configurations, URL composition, cost uncertainty, parameter variability, the branded-versus-custom rule, and the deprecated unknown-name-with-URL compatibility path. Add no CLI command: `inferencefit validate` checks the contract and `inferencefit benchmark` calls the same public engine. Update the canonical packaged Agent Skill and its existing preset-selection reference minimally: prefer a branded adapter; use `custom` only for a supplied/documented OpenAI-compatible endpoint; never invent URLs, read or expose credential values, or perform provider discovery. Keep exactly three existing presets and three skill references.

Set the single package version source and version-pinned CI/TestPyPI checks to `0.2.2`; preserve tag-derived production publishing, historical 0.1.0/0.2.0/0.2.1 docs, and serialized `schema_version: "0.1"`. Distribution checks must prove the updated skill remains in wheel and sdist; the generic example is a source-tree example, not a required wheel resource. Do not require an external paid key or live internet request. A deterministic local HTTP server may augment mocked HTTP tests.

Local arbitrary endpoints can reach localhost and private networks by design. Before any future hosted InferenceFit Cloud execution, a separate outbound-network/SSRF policy must be designed; 0.2.2 does not block these URLs or build Cloud. The user remains responsible for trusting an endpoint before sending benchmark prompts to it.

## Verification and explicit exclusions

Offline tests cover candidate validation and legacy dispatch; exact request URL, model, parameters, Bearer/no-Bearer, response normalization, missing optional fields, all specified errors, timeout/retry, secret redaction, pricing versus unknown cost, and a temporary spec calling public `benchmark()` with only HTTP mocked. CLI validation/benchmark, fixture/presets/Agent Skill, branded providers, artifacts/resume/API, packaging, and installed distributions stay green. Release verification includes full pytest, Ruff lint/format, wheel and sdist, Twine, distribution audit, clean installations, installed CLI and generic offline smoke, preset/Skill smoke, secret scan, and diff check. Independent read-only review follows the complete diff; each accepted finding starts with a failing test, then the full final gate runs again.

Explicitly exclude other protocol families, Anthropic-compatible generic APIs, LCAI, blockchain/job providers, plugin or Python entry-point loading, user classes, Cloud/auth/billing, other-language SDKs, UI, model catalogs, web discovery, automatic rankings/pricing/key discovery, new presets, and arbitrary code execution.
