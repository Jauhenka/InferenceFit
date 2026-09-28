# Multi-Provider 0.2.0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship InferenceFit 0.2.0 with first-class OpenRouter, Gemini, and OpenAI support through the existing benchmark and artifact pipeline.

**Architecture:** Preserve the shared OpenAI-compatible chat transport for Gemini and existing providers, add a narrow OpenRouter specialization, and implement OpenAI against the native Responses API. Centralize built-in construction in one fixed registry while carrying optional provider/model/usage/cost metadata through the existing contracts with explicit cost provenance.

**Tech Stack:** Python 3.11+, Pydantic v2, httpx, pytest, pytest-asyncio, respx, Ruff, Hatch/build, Twine.

**Spec:** `docs/superpowers/specs/2026-09-27-multi-provider-0.2.0-design.md`

## Global Constraints

- Release version is `0.2.0`; serialized contract `schema_version` remains `0.1`.
- Add exactly OpenRouter, Gemini, and OpenAI as new first-class providers.
- Live credentials use exactly `OPEN_ROUTER_API_KEY`, `GEMINI_API_KEY`, and `OPENAI_API_KEY`.
- OpenRouter base URL is `https://openrouter.ai/api/v1`; Gemini's canonical compatibility base URL is `https://generativelanguage.googleapis.com/v1beta/openai`; OpenAI Responses base URL is `https://api.openai.com/v1`.
- Native provider model identifiers are preserved without InferenceFit translation.
- Unit tests make no network requests; each live test skips cleanly without its own credential.
- Provider-reported cost is authoritative; configured pricing is a labeled fallback; pricing is never guessed.
- Missing optional usage, cost, model, or backend metadata must not fail successful text inference.
- Preserve Fireworks, DeepSeek, Ollama/vLLM presets, fixture, custom OpenAI-compatible, Python, CLI, HTTP API, artifact, resume, packaging, and release behavior.
- Do not add other providers, Cloud/auth/billing/payment/API-key hosting, UI, streaming, stateful conversations, tools, or a plugin/capability framework.

## Review Focus

- OpenAI Responses may emit reasoning or tool items before a message; Task 4 tests ordered extraction from typed output items rather than indexing the first item.
- A provider-reported cost of `0.0` must override nonzero configured pricing; Task 1 pins this precedence.
- Legacy observations omit every new optional field; Task 1 verifies they still deserialize with `schema_version: "0.1"`.
- HTTP bodies may echo credentials or prompts; Tasks 1–4 assert normalized errors expose status/safe code only.
- OpenAI token-limit aliases can conflict; Task 4 asserts conflicting aliases fail before HTTP as a non-retryable configuration error.

---

### Task 1: Shared normalized metadata, cost provenance, and HTTP errors

**Files:**
- Modify: `src/inferencefit/providers/base.py`
- Create: `src/inferencefit/providers/http_errors.py`
- Modify: `src/inferencefit/providers/openai_compatible.py`
- Modify: `src/inferencefit/contracts/observations.py`
- Modify: `src/inferencefit/execution/runner.py`
- Create: `tests/test_provider_contracts.py`
- Modify: `tests/test_completeness.py`
- Modify: `tests/test_engine.py`

**Interfaces:**
- Consumes: existing `CandidateSpec`, `ProviderResponse`, `ProviderError`, `TokenUsage`, `Observation`, `_cost()`, and `_execute()`.
- Produces: `ProviderResponse.total_tokens: int | None`, `cost_usd: float | None`, and
  `provider_backend: str | None`; `TokenUsage.total_tokens: int | None`; persisted
  `Observation.provider/model/provider_backend: str | None` and
  `cost_source: Literal["provider_reported", "configured_pricing"] | None`;
  `provider_error_from_response(response: httpx.Response, *, provider: str) -> ProviderError`.

- [ ] **Step 1: Write failing contract, cost, compatibility, and error tests**

Prove that total tokens and provider/model/backend persist; provider cost including `0.0` wins and records `provider_reported`; configured pricing records `configured_pricing`; absent metadata stays `None`; legacy observations still validate; 401/403 are non-retryable authentication/permission errors; 408, 429, and 5xx are retryable timeout/rate/server errors; transport timeouts/networks normalize safely; and a response body or token never appears in an exception or serialized error.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `python -m pytest tests/test_provider_contracts.py tests/test_completeness.py tests/test_engine.py -q`

Expected: failures identify missing fields, cost precedence/provenance, and shared error normalization.

- [ ] **Step 3: Implement optional contracts and one shared HTTP normalizer**

Append defaulted fields to the frozen `ProviderResponse` dataclass; add optional/defaulted fields to
the `TokenUsage` and `Observation` Pydantic models; copy normalized metadata in `_execute()`; and
select provider cost before `_cost()` without treating zero as missing. The error helper may parse
only a machine-readable code needed for classification and must never include the response body,
request headers, or credential in its message.

- [ ] **Step 4: Move the generic adapter onto the shared error path**

Keep its endpoint, payload, and response behavior intact while adding optional `usage.total_tokens` and generic actual-model normalization. Do not add vendor conditionals.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run: `python -m pytest tests/test_provider_contracts.py tests/test_completeness.py tests/test_engine.py -q`

Expected: all focused tests pass, including existing DeepSeek and custom-compatible coverage.

- [ ] **Step 6: Commit**

```bash
git add src/inferencefit/providers/base.py src/inferencefit/providers/http_errors.py src/inferencefit/providers/openai_compatible.py src/inferencefit/contracts/observations.py src/inferencefit/execution/runner.py tests/test_provider_contracts.py tests/test_completeness.py tests/test_engine.py
git commit -m "feat: normalize provider metadata and errors"
```

### Task 2: OpenRouter specialization

**Files:**
- Create: `src/inferencefit/providers/openrouter.py`
- Modify: `src/inferencefit/providers/openai_compatible.py`
- Modify: `src/inferencefit/providers/__init__.py`
- Modify: `src/inferencefit/credentials/__init__.py`
- Create: `tests/test_openrouter_provider.py`

**Interfaces:**
- Consumes: Task 1's extended response fields, shared transport hooks, and HTTP normalizer.
- Produces: `OpenRouterProvider(credential: str | None)` implementing `ProviderAdapter`; exact `OPEN_ROUTER_API_KEY` fallback; normalized OpenRouter backend and authoritative request cost.

- [ ] **Step 1: Write failing OpenRouter request/response/credential tests**

Cover native model and parameter pass-through, exact endpoint, Bearer plus `X-OpenRouter-Metadata: enabled`, text, prompt/completion/total tokens, actual model, `usage.cost`, selected endpoint provider, missing optional usage/cost/routing metadata, malformed responses, authentication, rate limit, timeout/network, server failure, retryability, and secret redaction. Assert the required credential spelling resolves and the legacy spelling alone does not.

- [ ] **Step 2: Run provider tests and verify RED**

Run: `python -m pytest tests/test_openrouter_provider.py tests/test_engine.py -q`

Expected: adapter and exact credential fallback are missing.

- [ ] **Step 3: Implement the thin specialization**

Add narrow request-header and response-metadata hooks to the compatible adapter, then use them in `OpenRouterProvider` for the fixed base URL, metadata opt-in, selected upstream provider, and `usage.cost`. Guard every optional structure so missing metadata remains successful.

- [ ] **Step 4: Fix credential resolution and exports**

Map `openrouter` only to `OPEN_ROUTER_API_KEY` and export `OpenRouterProvider`; do not accept an alias for the legacy spelling.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run: `python -m pytest tests/test_openrouter_provider.py tests/test_provider_contracts.py tests/test_completeness.py tests/test_engine.py -q`

Expected: all focused and generic compatibility tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/inferencefit/providers src/inferencefit/credentials tests/test_openrouter_provider.py
git commit -m "feat: add first-class OpenRouter provider"
```

### Task 3: Gemini compatible profile

**Files:**
- Modify: `src/inferencefit/providers/openai_compatible.py`
- Modify: `src/inferencefit/credentials/__init__.py`
- Create: `tests/test_gemini_provider.py`

**Interfaces:**
- Consumes: the shared compatible adapter and HTTP normalizer from Task 1.
- Produces: first-class `provider: gemini` through canonical preset `https://generativelanguage.googleapis.com/v1beta/openai` and exact `GEMINI_API_KEY` fallback.

- [ ] **Step 1: Write failing Gemini profile and credential tests**

Use `respx` against the exact `/chat/completions` URL. Cover Bearer auth, native Gemini model name, messages plus supported parameters, successful text, prompt/completion/total tokens, actual model, missing optional usage, malformed response, authentication, 429, timeout/network, 5xx, retryability, and secret redaction. Assert no Gemini-specific monetary cost is invented.

- [ ] **Step 2: Run Gemini tests and verify RED**

Run: `python -m pytest tests/test_gemini_provider.py tests/test_engine.py -q`

Expected: Gemini URL and credential fallback are absent.

- [ ] **Step 3: Add the minimal compatible profile**

Add only the Gemini preset and credential fallback. Reuse generic request, response, token, latency, and error logic; do not create a Gemini subsystem or claim support for unsupported parameters.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `python -m pytest tests/test_gemini_provider.py tests/test_completeness.py tests/test_engine.py -q`

Expected: Gemini and existing compatible-provider tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/inferencefit/providers/openai_compatible.py src/inferencefit/credentials/__init__.py tests/test_gemini_provider.py
git commit -m "feat: add first-class Gemini provider"
```

### Task 4: Native OpenAI Responses provider

**Files:**
- Create: `src/inferencefit/providers/openai_responses.py`
- Modify: `src/inferencefit/providers/__init__.py`
- Modify: `src/inferencefit/credentials/__init__.py`
- Create: `tests/test_openai_responses_provider.py`

**Interfaces:**
- Consumes: `CandidateSpec`, `TestCase`, Task 1's `ProviderResponse` and shared error normalizer.
- Produces: `OpenAIResponsesProvider(credential: str | None)` posting to `https://api.openai.com/v1/responses`; exact `OPENAI_API_KEY` fallback; message/input, output-text, token, model, and parameter normalization.

- [ ] **Step 1: Write failing OpenAI request and response tests**

Assert `model`, message-array `input`, `store: false`, temperature, native `max_output_tokens`, and one legacy token-limit alias map correctly without changing native model names. Test typed output where reasoning precedes one or more message/output-text items; input/output/total usage; actual model; no provider cost; missing optional usage; empty/malformed typed output; `status: incomplete`; authentication; temporary versus non-transient 429 codes where official semantics distinguish them; timeout/network; 5xx; retryability; and secret/body redaction.

- [ ] **Step 2: Write failing parameter-conflict tests**

Assert multiple token-limit aliases, or an alias plus a different native value, fail before HTTP with `ProviderError(kind="configuration", retryable=False)` and no payload/secret disclosure. Unsupported chat-only fields are not silently translated beyond the explicitly documented aliases.

Also assert `candidate.parameters` cannot override reserved `model`, `input`, or `store` fields.
After token-limit normalization, all other parameters are forwarded unchanged; unsupported
chat-only fields therefore receive the provider's normalized non-retryable client error rather
than being silently dropped.

- [ ] **Step 3: Run OpenAI tests and verify RED**

Run: `python -m pytest tests/test_openai_responses_provider.py tests/test_engine.py -q`

Expected: Responses adapter, credential fallback, and translation rules are absent.

- [ ] **Step 4: Implement the focused Responses adapter**

Post stateless requests, translate only the documented token aliases, and concatenate `output_text` content from typed message items in order. Normalize usage and actual model, leave monetary cost unset, and reuse shared latency/error behavior. Treat missing usable text and incomplete responses as normalized response errors.

- [ ] **Step 5: Add the credential fallback and export**

Map `openai` to `OPENAI_API_KEY` and export `OpenAIResponsesProvider` without adding an SDK dependency.

- [ ] **Step 6: Run focused tests and verify GREEN**

Run: `python -m pytest tests/test_openai_responses_provider.py tests/test_provider_contracts.py tests/test_engine.py -q`

Expected: all focused tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/inferencefit/providers/openai_responses.py src/inferencefit/providers/__init__.py src/inferencefit/credentials/__init__.py tests/test_openai_responses_provider.py
git commit -m "feat: add OpenAI Responses provider"
```

### Task 5: Central provider construction and cross-provider offline benchmark

**Files:**
- Create: `src/inferencefit/providers/registry.py`
- Modify: `src/inferencefit/providers/__init__.py`
- Modify: `src/inferencefit/core.py`
- Create: `tests/test_provider_registry.py`
- Create: `tests/test_multi_provider_benchmark.py`

**Interfaces:**
- Consumes: `FixtureProvider`, `OpenAICompatibleProvider`, `OpenRouterProvider`, `OpenAIResponsesProvider`, `EnvironmentCredentialResolver`, `CandidateSpec`, and a spec directory.
- Produces: `create_provider(candidate: CandidateSpec, *, spec_dir: Path, resolver: EnvironmentCredentialResolver) -> ProviderAdapter`; a fixed builder mapping for `openrouter`, `gemini`, and `openai`; explicit-`base_url` precedence and generic fallback for existing compatible providers.

- [ ] **Step 1: Write failing registry dispatch tests**

Assert fixture receives the spec directory; OpenRouter and OpenAI receive their specialized
classes; Gemini uses the compatible profile; Fireworks, DeepSeek, Ollama, vLLM, and custom base
URLs retain the generic adapter; an explicit `base_url` forces the generic compatible path even
when the provider name is `openrouter`, `gemini`, or `openai`; each non-fixture credential resolves
exactly once; and unknown providers without a base URL retain the existing request-time
configuration failure.

- [ ] **Step 2: Write a failing three-provider benchmark test**

Create a real temporary YAML spec and JSONL dataset with OpenRouter, Gemini, and OpenAI candidates. Mock only their HTTP endpoints, call public `benchmark()`, and assert successful persisted observations, provider/model/usage/cost provenance, completed result/manifest, no credential values or `credential_ref` in artifacts, and no vendor branch in core.

- [ ] **Step 3: Run registry and benchmark tests and verify RED**

Run: `python -m pytest tests/test_provider_registry.py tests/test_multi_provider_benchmark.py -q`

Expected: centralized construction and specialized dispatch are missing.

- [ ] **Step 4: Implement the fixed registry and simplify core**

Keep the mapping private and static. Resolve credentials inside `create_provider` except for
fixture. Check explicit `candidate.base_url` before built-in dispatch and return the generic adapter
for that path and for provider names outside the three new entries. Replace core's construction
loop branches with `create_provider` and import `__version__` for the manifest instead of adding
another release literal.

- [ ] **Step 5: Run integration plus existing engine/API tests**

Run: `python -m pytest tests/test_provider_registry.py tests/test_multi_provider_benchmark.py tests/test_engine.py tests/test_completeness.py -q`

Expected: all new and existing provider paths pass.

- [ ] **Step 6: Commit**

```bash
git add src/inferencefit/providers/registry.py src/inferencefit/providers/__init__.py src/inferencefit/core.py tests/test_provider_registry.py tests/test_multi_provider_benchmark.py
git commit -m "refactor: centralize provider construction"
```

### Task 6: Independent live benchmark smokes and examples

**Files:**
- Create: `tests/test_provider_live.py`
- Modify: `pyproject.toml`
- Create: `examples/lead_semantic_units/eval.openrouter.smoke.yaml`
- Create: `examples/lead_semantic_units/eval.gemini.smoke.yaml`
- Create: `examples/lead_semantic_units/eval.openai.smoke.yaml`
- Modify: `examples/lead_semantic_units/README.md`

**Interfaces:**
- Consumes: public `benchmark()`; the three provider keys and optional model overrides.
- Produces: marker `provider_live`; independent live tests defaulting to `openrouter/free`, `gemini-3.5-flash-lite`, and `gpt-6-luna`.

- [ ] **Step 1: Write three independently skipped live tests**

Create `test_openrouter_live_benchmark`, `test_gemini_live_benchmark`, and
`test_openai_live_benchmark`. Each checks only its own credential before setup, chooses its
provider-specific override or documented default, writes a one-case temporary workload whose user
message is `Reply with only OK.`, and calls `benchmark()`. Use `max_tokens: 32` for OpenRouter and
Gemini and native `max_output_tokens: 64` for OpenAI. Assert a successful non-empty persisted
observation/result plus returned usage when present. Do not print or serialize environment values.

- [ ] **Step 2: Verify all absent-key paths without network**

Run with the three keys unset: `python -m pytest tests/test_provider_live.py -m provider_live -q`

Expected: three clean skips and zero HTTP calls.

- [ ] **Step 3: Add concise provider smoke examples and commands**

Mirror the existing lead example contract with native model names and provider-appropriate token-limit parameters. Include credential references only, never values. Explain that model/parameter availability changes and show the override variables for live pytest.

- [ ] **Step 4: Commit**

```bash
git add tests/test_provider_live.py pyproject.toml examples/lead_semantic_units
git commit -m "test: add multi-provider live benchmark smokes"
```

### Task 7: Version 0.2.0, documentation, and release safety

**Files:**
- Modify: `src/inferencefit/__init__.py`
- Modify: `src/inferencefit/api/__init__.py`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `docs/contracts.md`
- Create: `docs/releases/0.2.0.md`
- Modify: `.github/workflows/ci.yml`
- Modify: `.github/workflows/testpypi.yml`
- Modify: `scripts/audit_distribution.py`
- Modify: `tests/test_release_metadata.py`
- Modify: `tests/test_release_smoke.py`
- Modify: `tests/test_distribution_audit.py`
- Modify: `tests/test_ci_workflows.py`

**Interfaces:**
- Consumes: completed provider behavior and the existing single-source version convention.
- Produces: runtime/package/API/manifest/CI version `0.2.0`; supported-provider and contract documentation; release notes; secret scanning for the three new live credential names.

- [ ] **Step 1: Write failing version, documentation, and secret-audit assertions**

Require 0.2.0 from the single maintained source and runtime consumers; fixed CI/TestPyPI artifact
checks for 0.2.0; README coverage of Fireworks, DeepSeek, OpenRouter, Gemini, OpenAI, the
fixture/testing provider, and the preserved Ollama/vLLM and custom-compatible paths, exact three
new key names, minimal configs, live command, and
model-parameter caveat; contract docs that explicitly describe the additive optional 0.2.0 fields
while retaining `schema_version: "0.1"`; and audit rejection of real assignments to
`OPEN_ROUTER_API_KEY`, `GEMINI_API_KEY`, and `OPENAI_API_KEY` while allowing placeholders.

- [ ] **Step 2: Run release-focused tests and verify RED**

Run: `python -m pytest tests/test_release_metadata.py tests/test_release_smoke.py tests/test_distribution_audit.py tests/test_ci_workflows.py -q`

Expected: failures identify 0.1.0 literals, stale documentation, and incomplete secret patterns.

- [ ] **Step 3: Apply version and multi-provider documentation updates**

Set `__version__` to 0.2.0 and make API/manifest consumers import it. Update current CI/TestPyPI artifact expectations, README, changelog, contracts, examples index, and 0.2.0 release notes. Preserve historical 0.1.0 documentation and test fixtures whose purpose is historical rather than current-version verification.

- [ ] **Step 4: Extend the distribution secret audit narrowly**

Recognize the exact new key assignments and add mutation coverage, without removing existing provider/key protections or treating documented placeholders as secrets.

- [ ] **Step 5: Run release-focused tests and verify GREEN**

Run: `python -m pytest tests/test_release_metadata.py tests/test_release_smoke.py tests/test_distribution_audit.py tests/test_ci_workflows.py -q`

Expected: all focused tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/inferencefit README.md CHANGELOG.md docs/contracts.md docs/releases/0.2.0.md .github/workflows scripts/audit_distribution.py tests
git commit -m "chore: prepare multi-provider 0.2.0 release"
```

### Task 8: Full verification, live execution, secret audit, and review

**Files:**
- Modify only for defects reproduced by a failing test.

**Interfaces:**
- Consumes: Tasks 1–7.
- Produces: fresh offline, package, optional live, scope, and independent-review evidence.

- [ ] **Step 1: Run the complete offline suite**

Run: `python -m pytest -q`

Expected: all offline tests pass; the three live tests skip when their keys are absent.

- [ ] **Step 2: Run lint and formatting checks**

Run: `python -m ruff check .`

Run: `python -m ruff format --check .`

Expected: both exit 0.

- [ ] **Step 3: Build and validate the distribution**

Run: `python -m build`

Run: `python -m twine check dist/*`

Run: `python scripts/audit_distribution.py dist --expected-version 0.2.0`

Run the existing clean wheel and sdist installation verifiers against the generated 0.2.0 artifacts.

Expected: every command exits 0.

- [ ] **Step 4: Run each authorized live provider independently**

Check only key presence. For each available key, run its named test from
`python -m pytest tests/test_provider_live.py::test_openrouter_live_benchmark -q -s`,
`python -m pytest tests/test_provider_live.py::test_gemini_live_benchmark -q -s`, or
`python -m pytest tests/test_provider_live.py::test_openai_live_benchmark -q -s`. Record the
provider and override/default model and verify the persisted observation/result. Record a clean
skip for each missing key; never print credential values.

- [ ] **Step 5: Inspect scope, diff, and secrets**

Run `git diff --check`, inspect `git status --short` and `git diff --stat`, review every changed
file, and run the package secret audit. Confirm only OpenRouter, Gemini, and OpenAI were added;
excluded providers/features remain absent from provider registration and user-facing 0.2.0 scope;
only the three named new live credentials are assumed; and the user's existing `LICENSE`,
`AGENTS.md`, and `.github/copilot-instructions.md` changes remain untouched.

- [ ] **Step 6: Request independent DeepSeek review and verify every finding**

Delegate a read-only review of the final diff for requirements, provider boundaries, compatibility,
retryability, secret leakage, missing tests, and release scope. Check findings against code and rerun
affected verification before accepting any change.

- [ ] **Step 7: Commit verified test-first fixes and prepare the report**

Report files changed, architecture, tests, exact commands/results, per-provider live status/model,
limitations, and follow-up recommendations. Do not claim completion without fresh command evidence.
