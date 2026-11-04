# InferenceFit Cloud client M2 implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `inferencefit-cloud` a first-class, billable provider in the existing public benchmark workflow.

**Architecture:** A focused Cloud adapter calls the M1 HTTP API through a fixed trusted-origin policy. The runner supplies a durable run-scoped invocation identity through an optional provider capability. Final customer charge comes from Cloud request status, never local token pricing.

**Tech Stack:** Python 3.11+, Pydantic, httpx, Typer, pytest/respx, existing schema 0.1.

**Spec:** `docs/superpowers/specs/2026-10-12-inferencefit-cloud-client-m2-design.md`

## Global constraints

- Change the public OSS repository only; the private Cloud backend is read-only.
- Do not tag, publish, make paid requests, or claim Cloud production readiness.
- Cloud token source is `INFERENCEFIT_CLOUD_TOKEN` or an existing opaque `credential_ref`.
- Cloud candidate `base_url` and local `pricing` are rejected; endpoint trust is configured outside benchmark input.
- Existing `ProviderAdapter.complete` and artifact schema 0.1 remain compatible.
- Same logical invocation always reuses one Cloud idempotency key, including runner retries and resume.
- Final `Observation.cost_usd` is the settled Cloud customer charge, or unknown; never a reservation, quote, local token estimate, or zero by default.

## Review focus

1. A malicious Cloud `base_url` must fail before the bearer token can leave the trusted client.
2. Identical prompts in distinct runs with the same human run ID must use distinct idempotency keys.
3. A timeout after dispatch must not cause a retry with a fresh key.
4. A settled completion with an unavailable status lookup must retain output and unknown cost.
5. A resumed run with a missing observation must reuse the original Cloud key; an expired replay must not dispatch anew.

---

### Task 1: Credential, endpoint, and registration boundary

**Files:** `src/inferencefit/credentials/__init__.py`, `src/inferencefit/contracts/candidates.py`, `src/inferencefit/providers/registry.py`, new `src/inferencefit/providers/inferencefit_cloud.py`, `tests/test_inferencefit_cloud_provider.py`.

**Interfaces:** `CloudEndpoint.from_environment()` chooses a trusted origin; `create_provider()` returns `InferenceFitCloudProvider` for the canonical identifier. It consumes `EnvironmentCredentialResolver.resolve()`.

- [ ] Add failing tests for registration, missing token, `credential_ref`, Cloud `base_url` and `pricing` rejection, unauthorized HTTPS origin, loopback-only HTTP, and no redirect following.
- [ ] RED: `.venv/Scripts/python.exe -m pytest tests/test_inferencefit_cloud_provider.py -q`.
- [ ] Implement the minimum credential/endpoint policy and registry branch before generic URL handling. Never interpolate tokens in errors.
- [ ] GREEN: rerun the task tests and existing registry/credential tests.
- [ ] Commit: `feat: register secure Cloud provider boundary`.

### Task 2: Adapter contract and billing

**Files:** `src/inferencefit/providers/inferencefit_cloud.py`, `tests/test_inferencefit_cloud_provider.py`.

**Interfaces:** `InferenceFitCloudProvider.complete_with_invocation(candidate, case, repetition, invocation_id) -> ProviderResponse`; `complete()` generates a standalone identity. A shared read-only client method supports `/v1/models`, `/v1/account`, `/v1/quotes`, and `/v1/requests/{id}`.

- [ ] Add failing tests for body, authorization, stable key, opaque model ID, text/usage/finish/latency, optional metadata, settled `charged_micro_usd` conversion, absent charge, malformed success, error-code mapping, and secret redaction.
- [ ] RED: run `tests/test_inferencefit_cloud_provider.py`.
- [ ] Implement one HTTP path with redirects disabled, strict allowlisted parsing, and status lookup after success. Return unknown cost when the lookup cannot establish a settled charge.
- [ ] GREEN: rerun provider tests.
- [ ] Commit: `feat: normalize Cloud completions and customer charges`.

### Task 3: Run-scoped identity and retry recovery

**Files:** `src/inferencefit/core.py`, `src/inferencefit/execution/runner.py`, `src/inferencefit/providers/base.py` (optional capability only), `tests/test_inferencefit_cloud_idempotency.py`.

**Interfaces:** `run_evaluations(..., invocation_namespace: str | None = None)` computes an invocation digest from namespace/candidate/case/repetition. The runner calls optional `complete_with_invocation` when supported; existing adapters keep `complete`.

- [ ] Add failing tests for same-key retries, distinct repetitions, distinct runs with identical prompts and run IDs, resume after missing observation, 202 uncertainty, timeout, and no duplicate charge on same-key replay.
- [ ] RED: run `tests/test_inferencefit_cloud_idempotency.py`.
- [ ] Persist a random namespace in the 0.1 manifest before dispatch and reuse it on resume. Pass the stable identity through the optional provider capability; keep provider-neutral retry behavior for existing adapters.
- [ ] GREEN: rerun idempotency, runner, artifact, and resume tests.
- [ ] Commit: `feat: preserve Cloud invocation identity across retry and resume`.

### Task 4: Cloud CLI commands

**Files:** `src/inferencefit/cli/__init__.py`, new `src/inferencefit/cloud_client.py` if a focused shared API client is warranted, `tests/test_inferencefit_cloud_cli.py`.

**Interfaces:** `inferencefit cloud status|models|balance` reads M1 `/v1/account` and `/v1/models` and emits safe noninteractive text.

- [ ] Add failing CLI tests for configured, missing-token, invalid-token, unavailable-endpoint, models, balance, and absence of token in output.
- [ ] RED: run `tests/test_inferencefit_cloud_cli.py`.
- [ ] Implement Typer subcommands using the adapter's endpoint/credential policy and safe error mapping.
- [ ] GREEN: rerun CLI and existing CLI tests.
- [ ] Commit: `feat: inspect Cloud configuration and account from CLI`.

### Task 5: Mixed benchmark and actual backend contract

**Files:** `tests/test_inferencefit_cloud_benchmark.py`, `tests/test_inferencefit_cloud_backend_contract.py`.

**Interfaces:** Public `benchmark()` takes a real EvaluationSpec with fixture and Cloud candidates. The backend contract test imports the sibling Cloud FastAPI app read-only and mocks its upstream provider call.

- [ ] Add a failing mixed benchmark test for normal validators, observations, summary/ranking, customer cost, unchanged fixture cost, artifact secrecy, and resumed invocation reuse.
- [ ] Add a failing cross-repository smoke for the actual M1 routes and completion/status shapes; skip with an exact reason only if the sibling repo or its dependencies are unavailable.
- [ ] RED: run both new test modules.
- [ ] Make only integration corrections required by the real contract; record any backend change request separately, without editing Cloud.
- [ ] GREEN: rerun both tests and provider tests.
- [ ] Commit: `test: verify mixed Cloud benchmark and gateway contract`.

### Task 6: Agent guidance, example, packaging and review

**Files:** `src/inferencefit/skills/inferencefit/SKILL.md`, appropriate `references/*.md`, `README.md`, `examples/cloud-mixed/*`, release metadata only if preparing an explicit candidate, package tests.

**Interfaces:** A synthetic schema-0.1 fixture/Cloud example and documented operator-token workflow. No login/topup commands.

- [ ] Add documentation/skill assertions where repository convention uses them; confirm synthetic example validates and mentions consent, bounded spending, and unknown cost.
- [ ] RED: run targeted example/skill checks before docs are added.
- [ ] Update skill, example and README; inspect for stale "no Cloud" claims, credentials, invented model pricing, and private URLs.
- [ ] GREEN: run full offline pytest, Ruff lint/format, build, twine check, distribution audit, clean wheel and sdist installs, installed CLI smoke, `git diff --check`, and secret audit.
- [ ] Request independent read-only security/billing review; reproduce any accepted finding with a failing test, fix it, and rerun affected gates.
- [ ] Commit: `docs: explain optional Cloud benchmark workflow`.

## Release boundary

No release tag or PyPI upload. Keep the current package version during implementation unless the final distribution audit requires a deliberate prerelease candidate. Document unresolved M1 production gates and the confirmed official Cloud origin status in the final report.
