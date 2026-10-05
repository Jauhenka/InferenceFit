# Decentralized Inference Providers 0.2.3 Implementation Plan

**Goal:** Ship three small named OpenAI-compatible provider profiles, examples, live smoke checks, and release metadata while preserving the existing benchmark and schema contracts.

**Spec:** `docs/superpowers/specs/2026-10-05-decentralized-providers-0.2.3-design.md`

**Baseline:** 504 passed, 2 skipped, 3 deselected on the 0.2.2 checkout. Preserve pre-existing `LICENSE` and `.github/copilot-instructions.md` changes. Update the existing untracked `AGENTS.md` at the user's request.

## Task 1: Profiles and credentials

1. Add parameterized failing tests for canonical names, exact default URLs, shared adapter identity, Bearer fallback, `credential_ref` precedence, URL override, native model ID, and provider identity. Include safe missing-key behavior.
2. Run the focused tests and record RED.
3. Add three `PRESET_URLS` and three `_FALLBACKS`; do not add subclasses or redundant builders.
4. Run focused tests and record GREEN.

## Task 2: Public benchmark and shared HTTP behavior

1. Add failing parameterized public `benchmark()` tests for all three profiles: endpoint, auth, output, normalized usage/model, configured and unknown cost, artifact identity, and resolved-secret absence. Keep opaque `credential_ref` contract.
2. Run RED; implement only behavior actually missing; run GREEN. Reuse existing shared HTTP tests for 401/403, 429, timeout, 5xx, malformed responses, absent optional usage, and reserved `stream`; avoid multiplying equivalent tests by three.

## Task 3: Opt-in live smoke and examples

1. Add tests for any pure catalog-selection helper before implementing it: valid/current text model, unavailable/non-text entries, malformed catalog, empty catalog, and override. Limit it to `tests/` so explicit-model benchmarking never depends on a catalog.
2. Add `provider_live` checks that skip without each matching key, use a Chutes catalog choice or explicit override, require Morpheus and Nosana model overrides, confirm the Nosana override is currently served, make at most one catalog GET, and run one tiny public benchmark request with no retry or streaming. Record selected model without printing credentials.
3. Add one syntactically valid example spec and short guide per provider. Explain how to obtain a current native model ID; placeholders are not claimed available. Validate every example offline.

## Task 4: Guidance and release

1. Add failing documentation/metadata assertions for README, contracts, examples index, Skill, release notes, changelog, version, CI/TestPyPI checks, and AGENTS MCP working environment.
2. Run RED, update documents and metadata, run GREEN. Keep Skill changes minimal and historical releases intact. Retain schema version `0.1`.
3. Extend offline installed distribution smoke just enough to prove the three names resolve to the shared adapter and examples parse; preserve fixture, custom, presets, and Skill smoke.

## Task 5: Independent review and final gate

1. Ask DeepSeek for an independent read-only diff review, then inspect every finding and write a failing test before fixing accepted defects.
2. Run full pytest, Ruff check, and Ruff format check. Build a fresh wheel and sdist; run Twine check and distribution audit for `0.2.3`.
3. Verify clean wheel and sdist installs and installed CLI smoke. Check provider profiles, existing custom smoke, presets, packaged Skill, secret-safety assertions, `git diff --check`, and the complete diff against the base commit.
4. Run each opt-in live smoke only if its matching key is available, with one tiny request. If network or service access is blocked, record the exact limitation without treating offline verification as live success.
5. Rerun the complete gate after any review fix. Do not publish or push without authorization.
