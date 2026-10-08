# Native Anthropic (Claude) 0.2.4 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Add native Claude benchmarking through canonical `anthropic` and alias `claude` without changing other provider paths.

**Architecture:** Register both names in the central provider factory and credential resolver; one new adapter uses existing `httpx`, `ProviderResponse`, `ProviderError`, and engine retries. Keep model IDs opaque and schema version `0.1`.

**Tech Stack:** Python 3.11+, Pydantic, httpx, pytest/respx, Ruff, Hatchling.

**Spec:** `docs/superpowers/specs/2026-10-08-anthropic-claude-0.2.4-design.md`

## Global Constraints

- Preserve pre-existing user edits in `AGENTS.md`, `LICENSE`, and `.github/copilot-instructions.md`.
- No Anthropic SDK dependency, streaming, model registry, model-only inference, or new schema fields.
- No billable external calls in the ordinary test suite; release version is `0.2.4`.
- Preserve the established explicit-`base_url` generic override and retry behavior.

## Review Focus

- A system message after a user turn must fail before HTTP rather than move to the front.
- A named message must fail before HTTP rather than silently drop its name.
- `parameters.stream`, `model`, `messages`, or `system` must not override the benchmark request.
- A content response with only tool/thinking blocks must be a safe response error.
- Cache usage must not be lost from normalized input tokens, and malformed counts must not become negative or boolean tokens.

---

### Task 1: Alias routing and credentials

**Files:** `tests/test_anthropic_provider.py`, `src/inferencefit/providers/registry.py`, `src/inferencefit/credentials/__init__.py`, `src/inferencefit/providers/__init__.py`.

**Interfaces:** `create_provider(CandidateSpec, spec_dir, resolver) -> AnthropicProvider` for either name without `base_url`; `EnvironmentCredentialResolver.resolve(reference, provider)` checks explicit reference then `ANTHROPIC_API_KEY`.

- [x] Add failing parameterized tests for both names, one adapter class, fallback and reference precedence, missing-key safety, and current `base_url` precedence.
- [x] Run focused RED tests; add minimal routing and fallback entries; run GREEN.

### Task 2: Native Messages transport

**Files:** `src/inferencefit/providers/anthropic.py`, `tests/test_anthropic_provider.py`.

**Interfaces:** `AnthropicProvider(credential: str | None).complete(candidate, case, repetition) -> ProviderResponse`.

- [x] Add failing mocked HTTP tests for leading system prompts, ordered user/assistant messages, optional temperature, `max_tokens` default/alias/conflict, reserved keys, named/interleaved/only-system messages, text blocks, response model, usage including cache counts, and no usable text.
- [x] Run RED; implement the smallest non-streaming httpx adapter; run GREEN.
- [x] Add failing safe 401/403/429/529/timeout/network/malformed-response tests and make them GREEN with shared normalization.

### Task 3: Public benchmark and discoverability

**Files:** `tests/test_anthropic_benchmark.py`, `examples/anthropic/{eval.yaml,cases.jsonl,README.md}`, `README.md`, `docs/contracts.md`, `examples/README.md`, `src/inferencefit/skills/inferencefit/SKILL.md`.

- [x] Add failing public `benchmark()` tests for both names, canonical observation identity, cost unknown/configured, artifact pipeline, and resolved-secret absence.
- [x] Run RED then GREEN without creating another engine path.
- [x] Add failing documentation/example assertions; add a minimal offline-valid example and concise Anthropic (Claude) guidance; run GREEN.

### Task 4: Release metadata and installed smoke

**Files:** `src/inferencefit/__init__.py`, `CHANGELOG.md`, `docs/releases/0.2.4.md`, `docs/releasing.md`, `.github/workflows/{ci.yml,testpypi.yml}`, `scripts/installed_distribution_smoke.py`, `scripts/audit_distribution.py`, relevant release tests.

- [x] Add failing version, docs, installed-dispatch, and archive-secret-scan assertions for 0.2.4 and `ANTHROPIC_API_KEY`.
- [x] Run RED; update metadata, smoke, and notes while preserving historical releases; run GREEN.

### Task 5: Review and final verification

- [x] Obtain independent DeepSeek read-only review, assess findings, and fix accepted defects test-first.
- [x] Run full pytest, Ruff check/format, fresh wheel+sdist build, Twine, distribution audit, and clean wheel/sdist install smoke.
- [x] Scan for resolved secret values; inspect the complete diff and `git diff --check`; rerun the full gate after fixes.
- [x] Commit only 0.2.4 files. Leave publishing, release tagging, and pre-existing user edits untouched.
