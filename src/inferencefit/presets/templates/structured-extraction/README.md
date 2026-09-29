Replace the sample cases with representative production examples before using the benchmark for model-selection decisions.

# Structured-extraction preset

This project is a plumbing check, not benchmark evidence. It demonstrates the smallest
offline evaluation for extracting a typed JSON object from synthetic records. A passing
fixture run confirms only that initialization, validation, and reporting are connected.

## How this project is organized

- `cases.jsonl` contains two synthetic records, their requests, and expected JSON objects.
- `eval.yaml` defines the `offline-fixture` candidate, validators, constraints, and bounded
  execution settings.
- `fixtures/sample.jsonl` contains deterministic responses keyed by case ID, so the
  benchmark runs without a network connection or credentials.

## Candidates and validators

The sole candidate uses the local `fixture` provider. Replace that candidate with models
you actually want to compare after confirming their current provider settings and access.

The `response-schema` validator requires all four typed fields and rejects additional
properties. The root `record-exact` validator then compares the entire output object with
the expected object. Root exact comparison is deliberately strict: field ordering does not
matter after JSON parsing, but every value and field must match.

## Running

From this directory, run:

```console
inferencefit validate eval.yaml
inferencefit benchmark eval.yaml
```

The fixture candidate uses one repetition, concurrency of one, a short timeout, and
bounded retries.

## Customizing safely

Replace the cases with representative source formats, expected fields, optionality, and
edge conditions from the real workload. Replace the candidate and then adapt the schema,
validators, constraints, and execution envelope to match the production contract.

Whole-object equality is useful when every field must be exact. For more tolerant tasks,
use field-level exact validators and numeric validators with explicit tolerances. Keep the
schema strict enough to catch missing or invented fields. Low temperature can improve
repeatability only where the selected model supports that parameter; do not assume every
provider or model accepts it.
