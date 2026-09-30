Replace the sample cases with representative production examples before using the benchmark for model-selection decisions.

# Coding preset

This project is a plumbing check, not benchmark evidence. It exists to prove that a
coding evaluation can be initialized, validated, and executed offline with the fixture
provider. The two bundled cases and their fixture responses are synthetic toy snippets;
they say nothing about the quality of any real model.

## How this project is organized

- `cases.jsonl` holds two synthetic code-generation cases. Each `request` asks for a
  small response shaped `{"code": "..."}` and each `expected` value carries the reference
  code string.
- `eval.yaml` declares the single `offline-fixture` candidate, the validators, the
  constraints, and the bounded execution settings.
- `fixtures/sample.jsonl` supplies canned responses keyed by `case_id` so the benchmark
  runs without network access or credentials.

## Candidates

There is exactly one candidate, `offline-fixture`, backed by the `fixture` provider and
the `fixture` model. It reads `fixtures/sample.jsonl` relative to this file. There is no
credential reference and no live endpoint, so the run never leaves the local machine.

## Validators

Both validators run for every case:

- `response-schema` is a `json_schema` routing gate. It requires an object with a required
  string `code` property and `additionalProperties: false`.
- `code-exact` is an `exact` validator that compares the model's `/code` pointer against
  the case's `/code` reference.

Expected outputs are brittle: exact string equality flags whitespace, formatting, and
stylistic differences even when the code is correct, and many coding tasks have no single
canonical answer. Prefer deterministic structural checks over naive expected outputs.

## Running

Run `inferencefit validate <this>/eval.yaml` and then
`inferencefit benchmark <this>/eval.yaml`. The fixture provider keeps the run reproducible
and offline, with one repetition, concurrency of one, a short timeout, and bounded retries.

## Customizing safely

Rename and add `cases` from real traffic, add or replace `candidate` entries with the models
you are comparing, and adjust the `validator` set, the constraints, and the execution
envelope. Keep the constraints requiring success until you deliberately want to observe
failure rates.

When you customize a coding benchmark, remember these guardrails:

- Treat exact expected outputs as brittle and supplement them with structural checks.
- Prefer trusted local Python validators. A `python` validator calls a `module:function`
  you control in your own codebase and is trusted code; keep it reviewed and in-tree.
- Reuse existing unit tests as validators where they already encode the specification.
- Keep generation bounded: cap tokens, retries, and concurrency so a runaway candidate
  cannot burn budget or time.
- Never blindly execute untrusted output. Generated code, shell snippets, or imports must
  not be run by the harness, and must never be evaluated outside a sandbox you control.
