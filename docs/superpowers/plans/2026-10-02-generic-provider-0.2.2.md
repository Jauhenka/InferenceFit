# Generic OpenAI-Compatible Provider 0.2.2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Release InferenceFit 0.2.2 with an explicit, safe, documented `custom` OpenAI-compatible endpoint through the existing benchmark path.

**Architecture:** Validate the existing `CandidateSpec` fields, make the fixed registry's generic route explicit while preserving legacy URL overrides, and harden the shared chat adapter. Keep credential resolution, runner, cost rules, observation schema, CLI commands, and branded adapters in place.

**Tech Stack:** Python 3.11+, Pydantic v2, httpx, pytest/pytest-asyncio/respx, Typer, Hatch/build, Twine, Ruff.

**Spec:** `docs/superpowers/specs/2026-10-02-generic-provider-0.2.2-design.md`

## Global Constraints

- Version is `0.2.2`; serialized `schema_version` stays `"0.1"`.
- The only new public provider identifier is `custom`; no alias, plugin framework, second engine, new CLI command, or new preset.
- `custom` requires an explicit HTTP(S) API base URL; append `/chat/completions`; allow HTTP to localhost/private endpoints and recommend HTTPS remotely.
- `credential_ref: example-main` resolves through the existing `INFERENCEFIT_CREDENTIAL_EXAMPLE_MAIN`; no direct environment-variable-name field or new secret storage. Omitting the ref is credentialless.
- No custom-header feature in this release. Never persist resolved credentials in specs, artifacts, logs, errors, examples, or the Agent Skill.
- Preserve named-provider explicit-`base_url` precedence and unknown-name-with-URL legacy execution; deprecate and warn visibly and safely for the latter. New configurations use `provider: custom`. Preserve unknown-name-without-URL request-time failure.
- Generic monetary cost uses existing configured pricing or remains unknown; do not interpret arbitrary response cost metadata as authoritative.
- Ordinary tests and the release smoke make no paid/internet provider request. Preserve all historical release docs and user changes present before implementation.

## File map

| Unit | Files and responsibility |
| --- | --- |
| Candidate contract | `src/inferencefit/contracts/candidates.py`: custom requirement and explicit URL validation; `tests/test_evaluation_spec.py`: schema cases. |
| Fixed dispatch | `src/inferencefit/providers/registry.py`: explicit custom path and legacy typo warning; `tests/test_provider_registry.py`: precedence and regressions. |
| Shared chat path | `src/inferencefit/providers/openai_compatible.py`: reserved request keys; `tests/test_provider_contracts.py` and new `tests/test_custom_provider_benchmark.py`: HTTP, errors, and public benchmark artifacts. |
| User guidance | `README.md`, `docs/contracts.md`, `examples/README.md`, new `examples/generic_openai_compatible/{README.md,eval.yaml,cases.jsonl}`, `src/inferencefit/skills/inferencefit/{SKILL.md,references/presets.md}`, `tests/test_agent_skill.py`, `tests/test_release_metadata.py`. |
| Release metadata | `src/inferencefit/__init__.py`, `CHANGELOG.md`, new `docs/releases/0.2.2.md`, `docs/releasing.md`, `.github/workflows/{ci.yml,testpypi.yml}`, `tests/{test_release_metadata.py,test_ci_workflows.py}`. Production `.github/workflows/release.yml` remains tag-derived. |
| Installed smoke | `scripts/installed_distribution_smoke.py`, `tests/test_release_smoke.py`: local-server generic CLI benchmark from an installed wheel/sdist. Existing `scripts/audit_distribution.py` and `scripts/verify_artifact_install.py` are reused, changing only if an observed failing test exposes a real 0.2.2 gap. |

## Review Focus

- A URL with userinfo, query, fragment, or a full `/chat/completions` path could persist a credential or duplicate the endpoint; Task 1 rejects each before run creation.
- `parameters.model` or `parameters.messages` could replace the declared candidate or benchmark case, and `parameters.stream` could switch response protocol; Task 3 proves rejection before HTTP.
- A typo such as `opneai` plus `base_url` could look first-class; Task 2 proves a visible warning while preserving legacy execution.
- A valid completion with missing or malformed optional usage must stay successful and have unknown cost; Task 3 covers it in the public benchmark path.
- A slow endpoint or retryable status must obey the common attempt cap and timeout without leaking response secrets; Task 3 covers both in persisted observations.

---

### Task 1: Validate the custom candidate and explicit API base URL

**Files:**
- Modify: `src/inferencefit/contracts/candidates.py`
- Modify: `tests/test_evaluation_spec.py`

**Interfaces:**
- Consumes: existing `CandidateSpec(id, provider, model, base_url, credential_ref, pricing, parameters, tags)` and `EvaluationSpec` parsing.
- Produces: a `CandidateSpec` after-validator (for example `_validate_endpoint(self) -> CandidateSpec`) that raises secret-safe `ValueError("custom provider requires base_url")` for missing/blank custom URL and `ValueError("invalid base_url")` for malformed supplied URLs. No new serialized field.

- [ ] **Step 1: Add failing contract tests.** Parameterize missing/empty/whitespace custom URLs; malformed schemes, host, port, userinfo, query, fragment, controls, and full `/chat/completions` URLs. Assert the exact safe error category without echoing the URL. Assert `http://localhost:8000/v1`, `http://127.0.0.1:11434/v1/`, `http://[::1]:8000/v1`, and `https://gateway.example.com/api` validate, model IDs remain opaque, `credential_ref` and pricing survive parsing, and branded candidates without `base_url` remain valid. Include an explicit URL on `openai` as a compatibility case.
- [ ] **Step 2: Run RED.** `python -m pytest tests/test_evaluation_spec.py -q`; new invalid-input cases must fail because the current model accepts arbitrary strings and permits custom without a URL.
- [ ] **Step 3: Implement minimal validation.** Use Pydantic `model_validator(mode="after")` and `urllib.parse.urlsplit`. Require absolute `http`/`https`, hostname and valid port; reject whitespace/control, userinfo, query/fragment, and a final `/chat/completions` path, case-insensitively after trailing slashes. Validate any supplied `base_url`, but require one only for `custom`. Keep the stored base URL unchanged so the existing adapter performs trailing-slash handling.
- [ ] **Step 4: Run GREEN.** `python -m pytest tests/test_evaluation_spec.py tests/test_provider_registry.py -q`; expect all focused tests to pass.
- [ ] **Step 5: Commit.** Stage only the two files and commit `feat: validate custom endpoint configuration`.

### Task 2: Make fixed registry dispatch explicit and visible

**Files:**
- Modify: `src/inferencefit/providers/registry.py`
- Modify: `tests/test_provider_registry.py`

**Interfaces:**
- Consumes: Task 1's validated `CandidateSpec`; existing `create_provider(candidate: CandidateSpec, *, spec_dir: Path, resolver: EnvironmentCredentialResolver) -> ProviderAdapter` and `OpenAICompatibleProvider`.
- Produces: explicit `custom` construction, unchanged single credential-resolution call, and `UserWarning` for an unknown provider with a supplied URL. The warning recommends `custom` but contains no user-controlled label, URL, credential reference, or token.

- [ ] **Step 1: Add failing dispatch tests.** Assert `custom` selects exactly `OpenAICompatibleProvider` with and without a reference; `openai`, `openrouter`, and `gemini` with explicit `base_url` still select plain shared chat transport; `fixture` bypasses credentials; every non-fixture resolves once. For `opneai` with URL, use `pytest.warns(UserWarning, match="custom")`, assert the route works and response provider remains `opneai`; without URL, retain the existing request-time `ProviderError`. Assert no warning for known IDs, including Fireworks, DeepSeek, Ollama, and vLLM.
- [ ] **Step 2: Run RED.** `python -m pytest tests/test_provider_registry.py -q`; the unknown-name warning assertion must fail against current silent fallback.
- [ ] **Step 3: Implement minimal dispatch.** Keep `base_url` precedence and existing preset/builder behavior. Recognize `custom` explicitly, derive the known-ID set from existing builders and `PRESET_URLS` plus `fixture`/`custom`, then warn only for unknown IDs with URL using `warnings.warn(..., UserWarning, stacklevel=2)`. Do not add an adapter or change credential fallback names.
- [ ] **Step 4: Run GREEN.** `python -m pytest tests/test_provider_registry.py tests/test_provider_live.py -q`; default pytest configuration keeps live requests excluded.
- [ ] **Step 5: Commit.** Stage only registry and its test; commit `feat: formalize custom provider dispatch`.

### Task 3: Harden the shared request and prove public benchmark behavior

**Files:**
- Modify: `src/inferencefit/providers/openai_compatible.py`
- Modify: `tests/test_provider_contracts.py`
- Create: `tests/test_custom_provider_benchmark.py`

**Interfaces:**
- Consumes: Tasks 1–2; `OpenAICompatibleProvider.complete(candidate, case, repetition) -> ProviderResponse`, `ProviderError`, `EnvironmentCredentialResolver`, public `inferencefit.benchmark(spec_path, *, output_root=...) -> ResultBundle`, and existing `respx` HTTP boundary.
- Produces: `ProviderError("reserved chat-completions parameter", kind="configuration")` before HTTP for `parameters.model` or `parameters.messages`; no new response/artifact schema.

- [ ] **Step 1: Add failing request tests.** For each reserved key (`model`, `messages`, `stream`, including `stream: true`), assert configuration error and zero HTTP calls. On a valid `custom` candidate, assert the exact `POST https://gateway.example.com/v1/chat/completions`, unchanged `some/model-name`, case messages, `parameters.max_tokens`, Bearer header from `INFERENCEFIT_CREDENTIAL_EXAMPLE_MAIN`, and no Authorization when `credential_ref` is omitted. Assert trailing `/` makes the same endpoint.
- [ ] **Step 2: Add response and error tests with mocked HTTP.** Assert text, prompt/completion/total tokens, actual returned model, latency, and success with absent/malformed optional usage. Cover 401, 403, 408, 429, 5xx, malformed JSON, malformed completion shape, `httpx.ReadTimeout`, `httpx.ConnectError`, and secret-bearing response bodies/headers. Pin kind/retryability and no secret in exception or persisted error. Keep unsupported arbitrary response metadata ignored.
- [ ] **Step 3: Add a real temporary-spec public benchmark test.** Write one JSONL case and YAML `EvaluationSpec` under `tmp_path`; call `await benchmark(spec_path, output_root=...)` with only the HTTP boundary mocked. Assert canonical `provider: custom`, native request model, returned model, normal observation/result/manifest/spec/summary files, attempts/latency/reliability, configured pricing and `cost_source`, and no **resolved secret value** in any artifact or captured log/error. Preserve the existing persistence contract for the opaque `credential_ref` identifier. A second credentialless candidate with incomplete usage must have `cost_usd is None` and aggregate unknown cost. Add 429→success and slow-response timeout cases to assert `provider_attempts`, retry cap/backoff behavior, and common timeout semantics. Use tiny backoff values or monkeypatch sleep; no live internet.
- [ ] **Step 4: Run RED.** `python -m pytest tests/test_provider_contracts.py tests/test_custom_provider_benchmark.py -q`; reserved-key tests must fail because the payload currently lets parameters override model/messages and forward `stream`. Any already-green E2E assertion records existing behavior; do not manufacture failures.
- [ ] **Step 5: Implement the guard.** Before constructing/sending a chat payload, reject the three reserved keys using the exact safe error above; otherwise retain current payload, response extraction, error normalization, and common runner unchanged.
- [ ] **Step 6: Run GREEN.** `python -m pytest tests/test_provider_contracts.py tests/test_custom_provider_benchmark.py tests/test_multi_provider_benchmark.py tests/test_openrouter_provider.py tests/test_gemini_provider.py -q`; expect all focused/provider regressions green.
- [ ] **Step 7: Commit.** Stage the three named files; commit `test: cover generic benchmark and harden chat request`.

### Task 4: Document the canonical example and update the Agent Skill

**Files:**
- Modify: `README.md`
- Modify: `docs/contracts.md`
- Modify: `examples/README.md`
- Create: `examples/generic_openai_compatible/README.md`
- Create: `examples/generic_openai_compatible/eval.yaml`
- Create: `examples/generic_openai_compatible/cases.jsonl`
- Modify: `src/inferencefit/skills/inferencefit/SKILL.md`
- Modify: `src/inferencefit/skills/inferencefit/references/presets.md`
- Modify: `tests/test_agent_skill.py`
- Modify: `tests/test_release_metadata.py`

**Interfaces:**
- Consumes: Task 1's schema and Tasks 2–3's actual dispatch; existing `load_evaluation_spec(path)` and unchanged CLI `validate`/`benchmark` commands.
- Produces: one source-tree example whose `eval.yaml` parses under schema `"0.1"`; unchanged three preset IDs and three packaged Skill references.

- [ ] **Step 1: Add failing content and example tests.** Assert README/contracts/example index and Skill together teach canonical `provider: custom`, an explicit base URL, credential ref mapping, credentialless localhost, branded-provider preference, unknown cost, target-dependent parameters, and that unknown provider names plus `base_url` are deprecated backward compatibility rather than new syntax. Assert no invented URL/key or secret-bearing URL/header/parameter. Assert the new example parses with `load_evaluation_spec`, has one synthetic case and native model ID, and contains only placeholder endpoint/model/credential names. Assert Skill reference count remains three and no nonexistent CLI command or new preset appears.
- [ ] **Step 2: Run RED.** `python -m pytest tests/test_agent_skill.py tests/test_release_metadata.py -q`; new documentation/example assertions must fail before prose and files are added.
- [ ] **Step 3: Write the example and guidance.** Keep `eval.yaml` a valid remote example with `provider: custom`, `base_url: https://api.example.com/v1`, `credential_ref: example-main`, bounded `parameters.max_tokens`, and optional example prices clearly identified as placeholders or omit prices to avoid a false quote. Explain `INFERENCEFIT_CREDENTIAL_EXAMPLE_MAIN` and show a separate credentialless `http://127.0.0.1:8000/v1` variant in its README. Keep vendor adapter guidance and deprecated unknown-name-with-URL caveat in README/contracts/release notes; add only a short escape-hatch rule to existing Skill files.
- [ ] **Step 4: Run GREEN.** `python -m pytest tests/test_agent_skill.py tests/test_release_metadata.py tests/test_evaluation_spec.py -q`; also run `inferencefit validate examples/generic_openai_compatible/eval.yaml` without setting a credential (validation does not send HTTP).
- [ ] **Step 5: Commit.** Stage only listed docs, example, Skill, and tests; commit `docs: teach generic OpenAI-compatible endpoints`.

### Task 5: Prepare versioned 0.2.2 release metadata

**Files:**
- Modify: `src/inferencefit/__init__.py`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Create: `docs/releases/0.2.2.md`
- Modify: `docs/releasing.md`
- Modify: `examples/README.md`
- Modify: `.github/workflows/ci.yml`
- Modify: `.github/workflows/testpypi.yml`
- Modify: `tests/test_release_metadata.py`
- Modify: `tests/test_ci_workflows.py`

**Interfaces:**
- Consumes: Tasks 1–4 and existing Hatch dynamic version from `src/inferencefit/__init__.py`.
- Produces: package/manifest/API version `0.2.2`; fixed CI/TestPyPI artifact checks for 0.2.2; unchanged tag-derived production release workflow and schema `"0.1"`.

- [ ] **Step 1: Add failing release assertions.** Update exact version and fixed workflow expectations to `0.2.2`. Require README link to `docs/releases/0.2.2.md`, changelog section, release notes describing custom endpoint/credential/header/cost/compatibility limits, and current release guide rehearsal/tag examples. Preserve assertions for historical 0.1.0/0.2.0/0.2.1 documents and all existing provider/preset/Skill content.
- [ ] **Step 2: Run RED.** `python -m pytest tests/test_release_metadata.py tests/test_ci_workflows.py -q`; new exact-version and notes assertions must fail on 0.2.1.
- [ ] **Step 3: Update release material.** Change only `inferencefit.__version__` as the maintained package version source; update current-version README/example/releasing text, CHANGELOG, new notes, and fixed `ci.yml`/`testpypi.yml` checks. Do not edit historical release documents, serialized schema, release tag derivation, publisher identity, or production approval gates. Merge carefully with pre-existing user edits in `tests/test_ci_workflows.py`.
- [ ] **Step 4: Run GREEN.** `python -m pytest tests/test_release_metadata.py tests/test_ci_workflows.py tests/test_release_smoke.py -q`; expect current version and historical-regression checks green.
- [ ] **Step 5: Commit.** Stage only the listed release files; inspect `git diff --cached` before committing `chore: prepare generic provider 0.2.2 release`.

### Task 6: Add installed generic-provider offline smoke

**Files:**
- Modify: `scripts/installed_distribution_smoke.py`
- Modify: `tests/test_release_smoke.py`

**Interfaces:**
- Consumes: installed `inferencefit` CLI, the script's existing `main(expected_version, source_root)` smoke, and normal `http.server.ThreadingHTTPServer` from the standard library.
- Produces: a deterministic localhost `/v1/chat/completions` response and a temporary credentialless custom spec benchmarked by the installed CLI outside the source checkout.

- [ ] **Step 1: Add failing smoke tests.** Extend script contract tests to require a local HTTP server request at the composed path, exact native model/body, no Authorization, a successful generic observation with `provider: custom`, and unknown cost when no pricing is configured. Preserve the fixture benchmark, three preset checks, and packaged Skill path assertions. Ensure server shutdown even on CLI failure.
- [ ] **Step 2: Run RED.** `python -m pytest tests/test_release_smoke.py -q`; new generic installed-smoke expectations must fail.
- [ ] **Step 3: Implement the smallest server smoke.** Start a loopback server on an ephemeral port, write one temporary case/spec, run `inferencefit validate` and `inferencefit benchmark` through the existing installed executable helper, inspect the new run's observation/result, then stop the server. No credential, paid endpoint, source-tree import, or new runtime dependency. Merge with pre-existing user edits in the script and test rather than replacing them.
- [ ] **Step 4: Run GREEN.** `python -m pytest tests/test_release_smoke.py tests/test_distribution_audit.py -q`; expect script and existing package resource tests green.
- [ ] **Step 5: Commit.** Stage only the script/test after reviewing the diff; commit `test: smoke custom endpoint from installed distribution`.

### Task 7: Full gate, independent review, and final diff

**Files:**
- Review: complete 0.2.2 diff and all files named in Tasks 1–6.
- Modify: only files necessary for reproduced, in-scope findings.

**Interfaces:**
- Consumes: the finished release branch and all repository audit/install scripts.
- Produces: a reviewed, fully verified release candidate. This task does not publish, tag, or upload it.

- [ ] **Step 1: Run the complete offline quality gate.** Run `python -m pytest`, `ruff check .`, and `ruff format --check .`; require zero failures. Do not select `provider_live`.
- [ ] **Step 2: Build and inspect fresh artifacts.** After verifying the exact repository `dist`/`build` targets before cleaning stale output, run `python -m build`, `python -m twine check dist/*`, and `python scripts/audit_distribution.py dist --expected-version 0.2.2`. Require one 0.2.2 wheel and one sdist, updated packaged Skill content, no internal `docs/superpowers` or secret-bearing files.
- [ ] **Step 3: Verify both clean installs and CLI smoke.** Run `python scripts/verify_artifact_install.py dist/inferencefit-0.2.2-py3-none-any.whl 0.2.2 .` and `python scripts/verify_artifact_install.py dist/inferencefit-0.2.2.tar.gz 0.2.2 .`. Require installed CLI help/fixture/preset/Skill regression smoke and the new generic localhost E2E smoke from each artifact.
- [ ] **Step 4: Run explicit source/artifact secret checks.** Run `python -m pytest tests/test_distribution_audit.py tests/test_agent_skill.py tests/test_custom_provider_benchmark.py -q` and search new docs/examples/artifacts for secret-like assignments and resolved credential test values. Inspect matches without printing environment values; variable names and placeholders are allowed, secret values are not.
- [ ] **Step 5: Request independent read-only DeepSeek review.** Supply the design, this plan, and the complete diff; ask for only actionable scope, compatibility, URL/security, credential, cost, installed-resource, test, and release findings. Lead engineer reproduces every accepted claim. For each accepted finding, write a failing test, run RED, make the minimal fix, and run focused GREEN. Record technical reasons for rejected findings.
- [ ] **Step 6: Inspect the final diff.** Record the implementation base commit before Task 1. Run `git status --short`, `git diff --check`, `git diff --check <base>...HEAD`, and inspect `git diff <base>...HEAD` plus unstaged/untracked files. Require only 0.2.2 scope; preserve pre-existing user changes in `LICENSE`, `scripts/installed_distribution_smoke.py`, `tests/test_ci_workflows.py`, `tests/test_release_smoke.py`, `AGENTS.md`, and `.github/copilot-instructions.md`. Do not conflate them with release work.
- [ ] **Step 7: Repeat Steps 1–4 after review fixes.** Earlier green output is not a final gate. Commit only accepted in-scope fixes after inspecting the staged diff; stop before publishing or tagging.
