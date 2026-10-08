# InferenceFit 0.2.5 Auditable Responses Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Support Anthropic multi-workspace keys and persist provider-native response metadata through the existing benchmark pipeline.

**Architecture:** Extend nullable fields on `ProviderResponse` and `Observation`; the runner copies them and the existing JSONL store handles persistence. Enrich Anthropic and the two existing HTTP adapter paths using a small shared metadata helper.

**Tech Stack:** Python 3.11+, Pydantic, httpx, pytest/respx, Ruff, Hatchling.

**Spec:** `docs/superpowers/specs/2026-10-08-auditable-provider-responses-0.2.5-design.md`

## Global Constraints

- Release 0.2.5; serialized schema remains `"0.1"`.
- Keep existing text, token totals, costs, latency, success/error, retries, and old artifact loading.
- Never persist credentials, request headers, or inferred hidden reasoning.
- No live billable requests, publication, or tag push.

## Review Focus

- Missing `ANTHROPIC_WORKSPACE_ID` omits the header instead of sending an empty value.
- A native response containing an echoed credential does not put it into new metadata fields.
- `output_tokens` remains total provider output, even when `reasoning_tokens` is supplied.
- An old observation without new keys loads with `None` defaults and can be resumed.
- Unknown finish reasons survive verbatim while normalized `finish_reason` is `None`.

---

### Task 1: Contract and persistence

**Files:** `src/inferencefit/providers/base.py`, `src/inferencefit/contracts/observations.py`, `src/inferencefit/execution/runner.py`, contract and storage tests.

- [x] Add failing round-trip and old-record tests for all nullable fields.
- [x] Run RED; add fields and runner copy; run GREEN.

### Task 2: Anthropic workspace and audit data

**Files:** `src/inferencefit/providers/anthropic.py`, `src/inferencefit/providers/metadata.py`, `tests/test_anthropic_provider.py`, benchmark tests.

- [x] Add failing mock tests for workspace header, aliases, stop reasons, request ID, thinking/text, cache usage, and secret-safe raw data.
- [x] Run RED; implement minimal extraction and sanitization; run GREEN.

### Task 3: Other existing HTTP adapters

**Files:** `src/inferencefit/providers/openai_responses.py`, `src/inferencefit/providers/openai_compatible.py`, focused provider tests.

- [x] Add failing tests for OpenAI Responses and Gemini/DeepSeek/Fireworks native metadata, including absent fields.
- [x] Run RED; enrich already-parsed responses without changing request behavior; run GREEN.

### Task 4: Release and verification

**Files:** version module, README, contracts, changelog, release notes, release workflow/guide/tests.

- [x] Add failing release/version and documentation tests; update 0.2.5 metadata and provider gaps; run GREEN.
- [x] Obtain independent DeepSeek review and assess findings.
- [x] Run full pytest, Ruff, wheel/sdist build, Twine, archive audit, clean installs, and staged diff review.
- [x] Commit only 0.2.5 files; preserve publication and tags for human approval.
