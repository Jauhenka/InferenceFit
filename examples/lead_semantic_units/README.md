# Lead semantic-unit extraction

This example evaluates deterministic extraction of ordered, typed facts from short inbound sales leads. All people, organizations, contacts, products, dates, and requirements are invented for this repository.

The production-derived files named in the E0.5 brief were not present in this checkout or its Git history. The dataset therefore implements the brief's requested structural properties—multiple units, ambiguity, missing facts, malformed fragments, duplicates, corrections, exclusions, ordering, and multilingual text—without claiming to reproduce unavailable source cases.

## Contract

Each response is a JSON object with one `units` array. Every unit has a `type` from the documented enum and a non-empty `value` copied from the lead. Ordering follows the lead; exact duplicates are collapsed; explicit corrections replace retracted facts. Greetings, signatures, current-state context, and unsupported inferences are omitted.

`response-schema` is the only runtime routing gate. `exact-units` compares the predicted array with hidden expected data and is evaluation-only.

## Files and commands

- `dataset.jsonl`: 24 English cases.
- `dataset.smoke.jsonl`: four representative cases for first-contact live checks.
- `dataset.multilingual.jsonl`: two cases each in Russian, Ukrainian, Belarusian, and Polish.
- `eval.fixture.yaml`: two illustrative fixture candidates plus a schema-gated cascade.
- `eval.multilingual.fixture.yaml`: offline multilingual coverage.
- `eval.*.smoke.yaml`: opt-in single-provider live specs; they contain credential references, never credentials.
- `eval.fireworks.yaml` and `eval.deepseek.yaml`: larger provider evaluation specs.

```powershell
inferencefit validate examples/lead_semantic_units/eval.fixture.yaml
inferencefit benchmark examples/lead_semantic_units/eval.fixture.yaml

# These commands spend provider credits and require the corresponding key.
inferencefit benchmark examples/lead_semantic_units/eval.fireworks.smoke.yaml
inferencefit benchmark examples/lead_semantic_units/eval.deepseek.smoke.yaml
inferencefit benchmark examples/lead_semantic_units/eval.openrouter.smoke.yaml
inferencefit benchmark examples/lead_semantic_units/eval.gemini.smoke.yaml
inferencefit benchmark examples/lead_semantic_units/eval.openai.smoke.yaml
```

The smoke specs use `OPEN_ROUTER_API_KEY`, `GEMINI_API_KEY`, and `OPENAI_API_KEY` through their credential references. Model catalogs and supported request parameters can change; check the provider's current model and API documentation if a default is unavailable. To select another model for a live pytest check, set `OPEN_ROUTER_TEST_MODEL`, `GEMINI_TEST_MODEL`, or `OPENAI_TEST_MODEL` respectively, then run `python -m pytest tests/test_provider_live.py -m provider_live -q`. Each check skips when its own provider key is absent.

The fixture outputs are deliberately illustrative. They demonstrate that a cheaper model can be fast yet fail exact extraction, and that only schema-invalid outputs trigger the runtime cascade. They are not copied from, or represented as, real provider responses.

Pricing is a point-in-time E0.5 snapshot. Fireworks uses the model page's standard input/output rates. DeepSeek uses the documented off-peak cache-miss input and output rates applicable to the validation window; actual charges can differ by cache status and peak period.
