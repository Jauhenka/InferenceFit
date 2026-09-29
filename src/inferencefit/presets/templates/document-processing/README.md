Replace the sample cases with representative production examples before using the benchmark for model-selection decisions.

# Document-processing preset

This project is a plumbing check, not benchmark evidence. It shows the smallest working
shape for a document task and proves that a document evaluation can be initialized,
validated, and executed offline with the fixture provider. The two bundled cases and their
fixture responses are synthetic and say nothing about any real model.

## How this project is organized

- `cases.jsonl` holds two short synthetic document-classification cases. Each `request`
  asks for a response shaped `{"label": "..."}` and each `expected` value carries the
  reference label.
- `eval.yaml` declares the single `offline-fixture` candidate, the validators, the
  constraints, and the bounded execution settings.
- `fixtures/sample.jsonl` supplies canned responses keyed by `case_id` so the benchmark
  runs without network access or credentials.

## Candidates

There is exactly one candidate, `offline-fixture`, backed by the `fixture` provider and the
`fixture` model, reading `fixtures/sample.jsonl` relative to this file. There is no
credential reference and no live endpoint.

## Validators

- `response-schema` is a `json_schema` routing gate requiring an object with a required
  string `label` and `additionalProperties: false`.
- `label-exact` is an `exact` validator comparing the model's `/label` pointer against the
  case's `/label` reference.

## Running

Run `inferencefit validate <this>/eval.yaml` and then
`inferencefit benchmark <this>/eval.yaml`. The fixture provider keeps the run reproducible
and offline, with one repetition, concurrency of one, a short timeout, and bounded retries.

## Customizing safely

Rename and add `cases` from real documents, add or replace `candidate` entries with the
models you are comparing, and adjust the `validator` set, the constraints, and the execution
envelope as needed.

This deterministic sample covers only classification-shaped work: picking a label from a
closed set for a short input. It is a starting shape only, and it does not generalize to
other document tasks:

- Document QA needs a representative question and answer set and groundedness checks, not a
  single label.
- Summarization needs coverage, faithfulness, and length criteria rather than exact label
  equality.
- Synthesis across several documents needs multi-input cases and cross-document consistency
  checks.
- Long-input work needs cases that actually exercise the context window, plus attention to
  truncation and cost.

These quality dimensions need task-specific cases and a quality rubric. Version 0.2.1 has
no built-in semantic judge, and exact or contains validators are not semantic evaluation,
so plan to supply your own trusted local validators for any task that needs judgment.
