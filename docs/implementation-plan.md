# InferenceFit E0 Implementation Plan

> **Execution:** Five sequential DeepSeek MCP coding workers implement the tasks below with test-first development. The lead agent reviews each mutation set and runs focused verification before starting the next worker.

**Goal:** Deliver a local-first Python 3.11+ benchmarking and deterministic LLM configuration optimizer usable through one shared core from Python, CLI, and FastAPI.

**Architecture:** A modular monolith keeps Pydantic public contracts at the center. Provider, validator, credential, and artifact-store boundaries are explicit adapters; metrics and optimization remain pure functions. A bounded asynchronous runner writes terminal observations incrementally, then aggregation produces open ResultBundle and RoutingPolicy artifacts.

**Stack:** Python 3.11+, Pydantic v2, httpx, FastAPI, Uvicorn, Typer, PyYAML, jsonschema, pytest, pytest-asyncio, respx, Ruff.

**Binding specification:** The complete user-provided InferenceFit E0 brief attached to the initiating Codex task. All serialized public formats use `schema_version: "0.1"`; credentials must never be serialized or logged.

## Dependency direction

```text
contracts <- dataset / credentials / validators / providers
contracts <- execution <- storage
contracts <- metrics <- optimization
contracts <- reporting
all above <- core <- Python API / CLI / FastAPI
```

Framework-facing modules may depend inward on the core; the core must not depend on CLI or FastAPI. The fixture provider and filesystem store are first-class adapters used by offline integration tests.

## Task 1 — Foundation, contracts, dataset, validators, credentials

**Primary files:** `pyproject.toml`, `LICENSE`, `src/inferencefit/contracts/**`, `src/inferencefit/dataset.py`, `src/inferencefit/validators/**`, `src/inferencefit/credentials/**`, focused tests under `tests/`.

- Scaffold the `src/` package, Apache-2.0 license, dev tooling, and minimal package exports.
- Define Pydantic v2 contracts for EvaluationSpec, TestCase/chat messages, CandidateSpec/pricing, observations, validation results, candidate/cascade summaries, ResultBundle, and RoutingPolicy.
- Enforce schema version 0.1, unique candidate/validator IDs, valid execution settings, and rejection of eval-only routing gates.
- Load JSONL datasets, reject duplicate case IDs, and compute a stable content hash.
- Implement RFC 6901 JSON Pointer access and validators: exact, regex, enum, JSON Schema, numeric tolerance, contains, and local Python callable. Structured validation failures are data, not exceptions.
- Resolve opaque credential references from normalized `INFERENCEFIT_CREDENTIAL_*` variables with documented provider fallbacks; never expose secret values.
- TDD cycle: write focused tests, observe expected failures, implement minimal behavior, and run the focused suite plus Ruff.

**Acceptance:** Contract/dataset/validator/credential tests cover valid and invalid configurations, every validator, runtime-capability rules, hashes, pointers, and secret-safe errors.

## Task 2 — Providers, bounded execution, observation persistence, resume

**Primary files:** `src/inferencefit/providers/**`, `src/inferencefit/execution/**`, `src/inferencefit/storage/**`, related tests.

- Define the small async ProviderAdapter contract and registry.
- Implement deterministic fixture responses with configurable raw output, latency, token usage, and provider failures without sleeping.
- Implement a non-streaming OpenAI-compatible `httpx` adapter plus OpenRouter, Fireworks, Ollama, vLLM, and arbitrary-endpoint preset behavior.
- Classify retryable connection/timeout/429/5xx failures and use bounded exponential backoff; semantic failures are never retried.
- Execute planned `(case, candidate, repetition)` units with bounded concurrency, timeout, cancellation, deterministic identities, terminal failed observations, and incremental persistence.
- Implement run IDs, manifests, atomic JSON/YAML writes, append-and-flush JSONL, dataset/spec snapshots, compatibility checks, and resume that skips terminal observation identities.
- Never persist credentials or treat internal programming errors as provider failures.

**Acceptance:** Tests prove fixture determinism, HTTP request/response normalization, retries, bounded scheduling, cancellation, artifact safety, and resume skipping completed units.

## Task 3 — Metrics, constraints, Pareto, ranking, cascades, result artifacts

**Primary files:** `src/inferencefit/metrics/**`, `src/inferencefit/optimization/**`, `src/inferencefit/reporting/**`, result/routing contract refinements, tests.

- Aggregate all required counts, rates, latency statistics, token totals, and honest nullable costs. Use deterministic nearest-rank percentiles.
- Evaluate hard constraints using end-to-end success for `min_success_rate`; record actual/required values and eligibility.
- Compute a deterministic nondominated Pareto frontier across quality, cost, p95 latency, and reliability while handling unknowns explicitly.
- Implement all five objectives, balanced-v1 weights, unrankable explanations for missing metrics, and deterministic tie-breaks.
- Simulate two-stage primary/fallback cascades only on provider errors or failed runtime-capable routing gates, reusing observations and accounting for sequential latency/cost.
- Produce structured ResultBundle, valid/non-routable policy behavior, and a presentation-only Markdown report.

**Acceptance:** Unit tests cover empty/error cases, cost unknowns, all constraints/objectives, balanced formula, repeated deterministic ranking, Pareto rules, the three critical cascade cases, routing policy safety, and report generation.

## Task 4 — Shared orchestration, CLI, daemon, offline example

**Primary files:** `src/inferencefit/core.py`, `src/inferencefit/__init__.py`, `src/inferencefit/cli/**`, `src/inferencefit/api/**`, `examples/basic/**`, integration/API tests.

- Create one async orchestration path used by `inferencefit.benchmark`, CLI, and background API jobs.
- Implement `validate`, `benchmark [--resume]`, and `serve` with concise lifecycle output and localhost default `127.0.0.1:8787`.
- Implement `/health`, run creation/status/result/cancel endpoints with queued/running/completed/failed/cancelled states.
- Build an offline classification example with cheap/weaker and strong/more-expensive fixture candidates and a runtime-valid fallback demonstration.
- Add a complete integration test from dataset through artifacts and a daemon endpoint test suite.

**Acceptance:** Offline validate/benchmark commands work without keys; Python, CLI, and API use the same core; all seven required artifacts are coherent; resume and cancellation behavior are exercised.

## Task 5 — Documentation, CI, acceptance hardening

**Primary files:** `README.md`, `docs/architecture.md`, `docs/contracts.md`, `.github/workflows/ci.yml`, tests and source files needed to close verified gaps.

- Document philosophy, quick start, fixture and OpenAI-compatible usage, contracts, validators and capability distinction, constraints/objectives, cascades, artifacts, APIs, privacy, limitations, and future E1 options without promising unimplemented features.
- Explain the local-first modular monolith, dependency direction, language-neutral contracts, credential precedence, percentile and Pareto semantics, balanced-v1, and unsandboxed local Python validators.
- Configure offline normal test/lint CI after dependency installation and optional explicitly gated live tests.
- Audit the full specification against implementation, add regression tests before every fix, run the complete suite, and resolve formatting/lint failures.

**Acceptance:** A fresh editable install works; `pytest`, `ruff check .`, and `ruff format --check .` pass; the offline example and daemon workflow pass; artifact and credential audits find no leaks.

## Lead-agent review and final verification

After every DeepSeek delegation, inspect the reported files and Git diff, run focused tests, inspect recovery records, and acknowledge only reviewed mutation transaction IDs. After Task 5, independently run:

```text
pip install -e ".[dev]"
pytest
ruff check .
ruff format --check .
inferencefit validate examples/basic/eval.yaml
inferencefit benchmark examples/basic/eval.yaml
```

Then start the daemon and exercise every required endpoint with the offline fixture workload, verify resume skips completed observations, inspect all generated artifacts, and search tracked/workspace files for likely credential strings. Completion is reported only from fresh observed evidence.
