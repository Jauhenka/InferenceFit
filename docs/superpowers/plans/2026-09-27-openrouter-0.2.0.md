# OpenRouter 0.2.0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship InferenceFit 0.2.0 with first-class, secret-safe OpenRouter support through the existing benchmark and artifact pipeline.

**Architecture:** Preserve the generic OpenAI-compatible transport and add a focused `OpenRouterProvider` specialization for metadata opt-in and upstream-backend normalization. Carry optional provider/model/usage/cost metadata through `ProviderResponse` into `Observation`, with authoritative provider cost taking precedence over explicitly marked configured-price calculations.

**Tech Stack:** Python 3.11+, Pydantic v2, httpx, pytest, pytest-asyncio, respx, Ruff, Hatch/build, Twine.

**Spec:** `docs/superpowers/specs/2026-09-27-openrouter-0.2.0-design.md`

## Global Constraints

- Release version is `0.2.0`; serialized contract `schema_version` remains `0.1`.
- OpenRouter credentials use exactly `OPEN_ROUTER_API_KEY`; never accept, print, persist, or log the old `OPENROUTER_API_KEY` spelling.
- The OpenRouter base URL is `https://openrouter.ai/api/v1`, and model IDs remain native `provider/model-name` strings.
- Unit tests make no network requests; live tests skip cleanly without `OPEN_ROUTER_API_KEY`.
- Missing optional usage, cost, model, or backend metadata must not fail an otherwise successful inference.
- Provider-reported cost is authoritative; configured pricing is only a labeled fallback and pricing is never guessed.
- Preserve Fireworks, DeepSeek, fixture, custom OpenAI-compatible, public Python, CLI, HTTP, and artifact behavior.

## Review Focus

- A configured `OPEN_ROUTER_API_KEY` must be the only provider fallback accepted; Task 2 tests both the accepted and legacy spellings.
- HTTP error bodies may echo credentials or prompts; Task 2 asserts normalized errors never include bodies or the token.
- OpenRouter may omit `usage`, `usage.cost`, or routing metadata; Task 2 exercises each missing-field shape.
- Provider-reported zero cost is valid and must override nonzero configured pricing; Task 1 pins this precedence.
- Resume and old observation artifacts lack the new optional fields; Task 1 round-trips legacy-shaped observations.

---

### Task 1: Normalized usage, provider metadata, and cost provenance

**Files:**
- Modify: `src/inferencefit/providers/base.py`
- Modify: `src/inferencefit/contracts/observations.py`
- Modify: `src/inferencefit/execution/runner.py`
- Modify: `tests/test_completeness.py`
- Modify: `tests/test_engine.py`

**Interfaces:**
- Consumes: existing `ProviderResponse`, `TokenUsage`, `Observation`, and `_execute()` flow.
- Produces: optional `ProviderResponse.total_tokens`, `ProviderResponse.cost_usd`, and `ProviderResponse.provider_backend`; optional persisted `Observation.provider`, `model`, `provider_backend`, and `cost_source`; `TokenUsage.total_tokens`.

- [ ] **Step 1: Write failing contract and runner tests**

Add focused tests proving: total tokens and actual provider/model/backend persist; a returned `cost_usd=0.0` wins over configured pricing and records `provider_reported`; absent returned cost uses configured pricing and records `configured_pricing`; absent token/cost metadata stays `None`; and a legacy observation document without new fields still validates.

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `python -m pytest tests/test_completeness.py tests/test_engine.py -q`

Expected: failures identify missing response/observation fields and cost precedence.

- [ ] **Step 3: Implement the minimal normalized fields and precedence**

Extend the dataclass and Pydantic models with optional/defaulted fields. In `_execute()`, derive `(cost_usd, cost_source)` from provider cost first and `_cost()` second, preserving a valid zero. Copy the candidate/provider response metadata into the observation without adding vendor-specific logic.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `python -m pytest tests/test_completeness.py tests/test_engine.py -q`

Expected: all focused tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/inferencefit/providers/base.py src/inferencefit/contracts/observations.py src/inferencefit/execution/runner.py tests/test_completeness.py tests/test_engine.py
git commit -m "feat: preserve provider usage and cost metadata"
```

### Task 2: OpenRouter adapter, credentials, and normalized failures

**Files:**
- Create: `src/inferencefit/providers/openrouter.py`
- Modify: `src/inferencefit/providers/openai_compatible.py`
- Modify: `src/inferencefit/providers/__init__.py`
- Modify: `src/inferencefit/credentials/__init__.py`
- Create: `tests/test_openrouter_provider.py`
- Modify: `tests/test_engine.py`

**Interfaces:**
- Consumes: Task 1's extended `ProviderResponse` and the existing `CandidateSpec`/`TestCase` request shape.
- Produces: `OpenRouterProvider(credential: str | None)` implementing `ProviderAdapter`; exact `OPEN_ROUTER_API_KEY` resolution; reusable normalized HTTP status handling in the shared adapter.

- [ ] **Step 1: Write failing credential, request, response, and error tests**

Use `respx` and real adapter code to cover: native model ID and parameter pass-through; Bearer and `X-OpenRouter-Metadata: enabled` headers; response text; prompt/completion/total tokens; `usage.cost`; actual model; selected endpoint provider; no optional usage/cost/metadata; 401 authentication; 429 rate limit; 400 client error; 5xx provider error; HTTP timeout/network timeout; malformed JSON/choice/content; and response-body/token redaction. In credential tests, assert `OPEN_ROUTER_API_KEY` resolves and `OPENROUTER_API_KEY` alone does not.

- [ ] **Step 2: Run provider tests and verify RED**

Run: `python -m pytest tests/test_openrouter_provider.py tests/test_engine.py -q`

Expected: failures show the missing adapter, wrong fallback name, and incomplete metadata/error normalization.

- [ ] **Step 3: Add narrow shared hooks and the OpenRouter specialization**

Refactor `OpenAICompatibleProvider` only enough to support overridable request headers and optional response metadata. Keep generic text/token/model parsing shared. Add `OpenRouterProvider` to opt into routing metadata and select the endpoint entry whose `selected` value is true. Normalize statuses without including response text: authentication is non-retryable; 429 is `rate_limit` and retryable; 408/524 and transport timeouts are `timeout` and retryable; 5xx/529 are retryable provider HTTP errors; other 4xx errors are non-retryable HTTP errors.

- [ ] **Step 4: Fix the exact credential fallback and exports**

Change only the OpenRouter fallback to `OPEN_ROUTER_API_KEY`; export `OpenRouterProvider`. Do not add aliases for the legacy spelling.

- [ ] **Step 5: Run provider tests and verify GREEN**

Run: `python -m pytest tests/test_openrouter_provider.py tests/test_engine.py tests/test_completeness.py -q`

Expected: all focused tests pass, including existing DeepSeek and generic-adapter tests.

- [ ] **Step 6: Commit**

```bash
git add src/inferencefit/providers src/inferencefit/credentials tests/test_openrouter_provider.py tests/test_engine.py
git commit -m "feat: add first-class OpenRouter provider"
```

### Task 3: Provider registration and end-to-end offline benchmark coverage

**Files:**
- Modify: `src/inferencefit/core.py`
- Create: `tests/test_openrouter_benchmark.py`

**Interfaces:**
- Consumes: `OpenRouterProvider` from Task 2 and Task 1 observation fields.
- Produces: provider selection for `candidate.provider == "openrouter"` through the normal `benchmark()` path, with generic handling retained for all other non-fixture candidates.

- [ ] **Step 1: Write a failing offline benchmark test**

Patch only the HTTP boundary with `respx`, load a real temporary YAML spec and JSONL dataset using `provider: openrouter`, and call public `benchmark()`. Assert the OpenRouter endpoint/header/model, completed result, persisted observation metadata/cost source, manifest credential exclusion, and result compatibility. Add a missing-key benchmark test that fails before HTTP without exposing any secret value.

- [ ] **Step 2: Run the benchmark test and verify RED**

Run: `python -m pytest tests/test_openrouter_benchmark.py -q`

Expected: provider construction still selects the generic adapter or persisted metadata is absent.

- [ ] **Step 3: Register the specialized provider**

Add the smallest provider factory branch in `core.py`: fixture stays unchanged, OpenRouter gets `OpenRouterProvider`, and every other remote provider keeps `OpenAICompatibleProvider`. Import the package version instead of adding another release literal while touching manifest creation.

- [ ] **Step 4: Run the benchmark test and existing engine tests**

Run: `python -m pytest tests/test_openrouter_benchmark.py tests/test_engine.py -q`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/inferencefit/core.py tests/test_openrouter_benchmark.py
git commit -m "feat: route OpenRouter through benchmark pipeline"
```

### Task 4: Opt-in live smoke and example specs

**Files:**
- Create: `tests/test_openrouter_live.py`
- Modify: `pyproject.toml`
- Create: `examples/lead_semantic_units/eval.openrouter.yaml`
- Create: `examples/lead_semantic_units/eval.openrouter.smoke.yaml`
- Modify: `examples/lead_semantic_units/README.md`

**Interfaces:**
- Consumes: public `benchmark()` plus `OPEN_ROUTER_API_KEY` and optional `OPEN_ROUTER_TEST_MODEL`.
- Produces: pytest marker `openrouter_live` and a one-command real end-to-end benchmark check defaulting to `openrouter/free`.

- [ ] **Step 1: Write the live test with a credential skip gate**

The test must call `pytest.skip` before benchmark setup when `OPEN_ROUTER_API_KEY` is absent. With a key, create a one-case deterministic temporary workload, choose `os.environ.get("OPEN_ROUTER_TEST_MODEL", "openrouter/free")`, cap completion output, call `benchmark()`, and assert one successful observation, non-empty text, actual model, and available usage fields without requiring optional metadata.

- [ ] **Step 2: Verify the absent-key path**

Run in an environment with the key unset: `python -m pytest tests/test_openrouter_live.py -q`

Expected: one clean skip and no network request.

- [ ] **Step 3: Add concise full/smoke example specs and commands**

Mirror existing provider examples, use `provider: openrouter`, `credential_ref: openrouter-main`, a native model ID, small output bounds, and no invented local pricing for the free router. Document that users may replace the model and parameters according to model capabilities.

- [ ] **Step 4: Commit**

```bash
git add tests/test_openrouter_live.py pyproject.toml examples/lead_semantic_units
git commit -m "test: add OpenRouter live benchmark smoke"
```

### Task 5: Version 0.2.0 and user-facing documentation

**Files:**
- Modify: `src/inferencefit/__init__.py`
- Modify: `src/inferencefit/api/__init__.py`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `.github/workflows/ci.yml`
- Modify: `.github/workflows/testpypi.yml`
- Modify: `tests/test_release_metadata.py`
- Modify: `tests/test_ci_workflows.py`
- Modify: release-version expectations in `tests/test_distribution_audit.py` and `tests/test_release_smoke.py`
- Create: `docs/releases/0.2.0.md`
- Modify: `docs/contracts.md`

**Interfaces:**
- Consumes: the completed OpenRouter behavior and existing single-source version convention.
- Produces: runtime/package/API/manifest/CI version `0.2.0`, concise OpenRouter setup documentation, and release notes.

- [ ] **Step 1: Write or update failing version and documentation assertions**

Require the single maintained version source to report `0.2.0`, API health and manifest paths to consume that value, CI package verification to target 0.2.0 artifacts, README to contain `OPEN_ROUTER_API_KEY` and not `OPENROUTER_API_KEY`, and public contract docs to describe the optional observation metadata and cost provenance.

- [ ] **Step 2: Run release/CI tests and verify RED**

Run: `python -m pytest tests/test_release_metadata.py tests/test_release_smoke.py tests/test_distribution_audit.py tests/test_ci_workflows.py -q`

Expected: failures identify 0.1.0 release literals and stale OpenRouter documentation.

- [ ] **Step 3: Apply the 0.2.0 version and documentation updates**

Set `src/inferencefit/__init__.py` to 0.2.0 and make runtime consumers import `__version__`. Update fixed CI/TestPyPI artifact expectations, test fixtures that intentionally model the current distribution, README provider/config/live-test guidance, changelog, contract docs, and 0.2.0 release notes. Preserve historical 0.1.0 release documentation and history fixtures where they intentionally describe that release.

- [ ] **Step 4: Run release/CI tests and verify GREEN**

Run: `python -m pytest tests/test_release_metadata.py tests/test_release_smoke.py tests/test_distribution_audit.py tests/test_ci_workflows.py -q`

Expected: all focused tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/inferencefit README.md CHANGELOG.md .github/workflows tests docs/contracts.md docs/releases/0.2.0.md
git commit -m "chore: prepare InferenceFit 0.2.0"
```

### Task 6: Full verification, live execution, and secret audit

**Files:**
- Modify only if verification reveals a defect; every fix requires a reproducing failing test first.

**Interfaces:**
- Consumes: all previous tasks.
- Produces: fresh evidence for offline quality gates, package artifacts, optional live OpenRouter execution, and a clean scoped diff.

- [ ] **Step 1: Run the complete offline suite**

Run: `python -m pytest -q`

Expected: all tests pass; the live OpenRouter test is skipped when its key is absent.

- [ ] **Step 2: Run lint and formatting checks**

Run: `python -m ruff check .`

Run: `python -m ruff format --check .`

Expected: both exit 0 with no violations.

- [ ] **Step 3: Build and validate the distribution**

Run: `python -m build`

Run: `python -m twine check dist/*`

Run: `python scripts/audit_distribution.py dist --expected-version 0.2.0`

Run the existing clean wheel and sdist installation verifiers against the generated 0.2.0 artifacts.

Expected: all commands exit 0.

- [ ] **Step 4: Run the real OpenRouter path when authorized by the environment**

Check only whether `OPEN_ROUTER_API_KEY` exists; never print it. If present, run
`python -m pytest tests/test_openrouter_live.py -m openrouter_live -q -s` and record the value of
`OPEN_ROUTER_TEST_MODEL` or the default `openrouter/free`. If absent, record a clean skip and do not
attempt a live call.

- [ ] **Step 5: Inspect the diff and scan for credentials**

Run `git diff --check`, inspect `git status --short` and `git diff --stat`, review every changed
file, and use the repository's distribution/secret audit coverage. Verify that only this feature,
the 0.2.0 version bump, tests, examples, and documentation changed; preserve the user's existing
`LICENSE`, `AGENTS.md`, and `.github/copilot-instructions.md` changes.

- [ ] **Step 6: Request independent DeepSeek review and verify its findings**

Delegate a read-only review of the final diff for requirement gaps, secret leakage, compatibility,
and missing tests. Check every finding against the code and rerun any affected verification before
accepting it.

- [ ] **Step 7: Commit any verified test-first fixes and prepare the implementation report**

Report files changed, architecture, tests, exact commands/results, live-test status/model, and
remaining limitations. Do not claim completion without the fresh command evidence above.
