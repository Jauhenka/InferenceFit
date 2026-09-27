# Task 6 report: independent live benchmark smokes and examples

## Outcome

Added three independently skipped live benchmark tests, registered the `provider_live` pytest marker, and added OpenRouter, Gemini, and OpenAI lead-extraction smoke specs with README instructions. The tests use the public `benchmark()` API, store artifacts only under pytest's temporary directory, and never print credentials.

No provider credentials were used and no live requests were made. Each test checks its own key before creating its temporary workload; with the keys absent, each skips before reaching `benchmark()` or the HTTP layer.

## Files changed

- `tests/test_provider_live.py`
- `pyproject.toml`
- `examples/lead_semantic_units/eval.openrouter.smoke.yaml`
- `examples/lead_semantic_units/eval.gemini.smoke.yaml`
- `examples/lead_semantic_units/eval.openai.smoke.yaml`
- `examples/lead_semantic_units/README.md`

The three tests use `Reply with only OK.` and independent key checks. Defaults are `openrouter/free`, `gemini-3.5-flash-lite`, and `gpt-6-luna`, with their provider-specific `*_TEST_MODEL` overrides. OpenRouter and Gemini use `max_tokens: 32`; OpenAI uses `max_output_tokens: 64`. Tests assert successful non-empty persisted observations, completed persisted results, and non-empty token usage when usage is reported.

The example specs use credential references only. The README documents the key variables, live commands, model override variables, and the fact that model and parameter availability may change.

## Verification

Before verification, the child PowerShell processes set `TEMP` and `TMP` to `.tmp` and removed `OPEN_ROUTER_API_KEY`, `GEMINI_API_KEY`, and `OPENAI_API_KEY` without displaying their values.

- `python -m pytest tests/test_provider_live.py -m provider_live -q`: 3 skipped, one pytest cache warning. All three skips identify the missing provider-specific key. There were no HTTP calls because each skip occurs before workload setup and benchmark invocation.
- `python -m pytest -p no:cacheprovider`: 292 passed, 3 skipped, one pre-existing `StarletteDeprecationWarning` about `httpx` with `starlette.testclient`.
- `ruff check --no-cache`: passed. Ruff printed access-denied warnings for inaccessible cache/temporary directories in this managed worktree.
- `ruff format --check --no-cache tests/test_provider_live.py`: passed; the file is already formatted. Repo-wide format checking was not used because Ruff attempts to treat YAML files as source.
- `python -m inferencefit.cli validate` for each of the three new smoke specs: all three valid, each with one candidate.

## Self-review and concerns

The live tests do not run when their corresponding key is missing and do not depend on other providers' credentials. The examples use provider-native model names and the requested token-limit fields. Only the six Task 6 files listed above plus this report are intended for the Task 6 commit.

Live provider/model compatibility remains intentionally unverified here; final authorized live execution is assigned to Task 8. Model availability and supported parameters may change, as documented in the README.

## Commit

Planned commit subject: `test: add multi-provider live benchmark smokes`
