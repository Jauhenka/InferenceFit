# InferenceFit

InferenceFit is a local-first toolkit for evaluating and selecting LLM configurations for a
specific workload. Instead of asking which model is universally "best," it runs your versioned
test cases against candidate providers and models, measures quality, reliability, latency, token
use, and cost, applies your hard constraints, and produces a deterministic recommendation and an
open routing policy.

InferenceFit 0.1.0 is a pre-1.0 release. Public APIs and serialized schemas may change before 1.0.

## Installation

InferenceFit requires Python 3.11 or newer.

```bash
pip install inferencefit
```

## Offline quick start

The repository includes a deterministic fixture workload that needs no API key and makes no
network requests. From a source checkout, run:

```bash
inferencefit validate examples/basic/eval.yaml
inferencefit benchmark examples/basic/eval.yaml
```

The example compares two fixtures and evaluates a schema-gated fallback cascade. The benchmark
prints the run ID, recommendation, and artifact directory under `.inferencefit/runs/`.

The same benchmark entry point is available from Python:

```python
import asyncio

from inferencefit import benchmark

result = asyncio.run(benchmark("examples/basic/eval.yaml"))
print(result.recommendation)
```

## Opt-in provider examples

Live examples are intentionally separate from the offline quick start. They make network requests
and can spend provider credits. Set the named environment variable in your shell, then explicitly
run the corresponding smoke spec:

```bash
# Requires FIREWORKS_API_KEY
inferencefit benchmark examples/lead_semantic_units/eval.fireworks.smoke.yaml

# Requires DEEPSEEK_API_KEY
inferencefit benchmark examples/lead_semantic_units/eval.deepseek.smoke.yaml
```

These specs use synthetic lead-extraction cases. See the
[example guide](examples/lead_semantic_units/README.md) and the
[E0.5 validation report](docs/e0.5-real-world-validation.md) for their contract, pricing snapshots,
and observed results.

## How evaluation works

An `EvaluationSpec` YAML file connects a JSONL dataset to candidates, validators, hard constraints,
an optimization objective, and bounded execution settings. Candidate pricing is an explicit
snapshot in USD per million input and output tokens; InferenceFit does not fetch prices.

Built-in validators cover exact values, regular expressions, enums, JSON Schema, numeric values,
containment, and local Python callables. Exact, numeric, and Python validators can use hidden
evaluation answers and are evaluation-only. Runtime routing gates must use runtime-capable checks,
such as JSON Schema. Local Python validators execute with the current process permissions and are
not sandboxed, so do not run untrusted validator code.

Each candidate is summarized with end-to-end success, provider reliability, p50/p95 latency,
input/output tokens, and configured cost. Hard constraints can exclude configurations by success,
error rate, latency, or cost. Remaining candidates appear on a Pareto frontier and are ranked by
`min_cost`, `min_latency`, `max_quality`, `max_reliability`, or the versioned `balanced` objective.

E0 also simulates one two-stage cascade. Fallback occurs only after a provider error or failure of a
runtime-capable routing gate; hidden expected answers are never production routing signals. If no
configuration satisfies the constraints, the result is explicitly non-routable.

## Results, artifacts, and resume

The Python API returns a `ResultBundle`. Every completed CLI or Python run also writes a versioned
run-artifact directory at `.inferencefit/runs/<run-id>/` with:

- `manifest.json` — provenance, settings, and lifecycle state;
- `spec.yaml` and `dataset.jsonl` — exact input snapshots;
- `observations.jsonl` — one flushed terminal record per planned evaluation;
- `result.json` — metrics, constraints, Pareto frontier, ranking, and recommendation;
- `summary.md` — a human-readable result summary;
- `routing-policy.yaml` — a single, fallback, or explicitly non-routable policy.

Interrupted compatible runs can reuse completed observations:

```bash
inferencefit benchmark examples/basic/eval.yaml --resume <run-id>
```

Resume checks the spec and dataset hashes before skipping completed
`(case, candidate, repetition)` identities.

## Providers and credentials

The `fixture` provider is deterministic and offline. The generic, non-streaming OpenAI-compatible
adapter accepts an explicit base URL and includes endpoint presets for Fireworks, DeepSeek,
OpenRouter, Ollama, and vLLM. It uses the providers' chat-completions-shaped HTTP interface without
vendor SDKs.

Credentials are resolved from opaque references. For example, `credential_ref: fireworks-main`
checks `INFERENCEFIT_CREDENTIAL_FIREWORKS_MAIN` and then `FIREWORKS_API_KEY`; DeepSeek similarly
falls back to `DEEPSEEK_API_KEY`, and OpenRouter to `OPENROUTER_API_KEY`. Secret values are not
written to run artifacts.

## Local daemon

```bash
inferencefit serve
```

The daemon defaults to `127.0.0.1:8787` and exposes health, run creation, status, result, and
cancellation endpoints. It has no authentication and is intended only for trusted localhost use;
do not expose it to a network.

## Current limitations

Version 0.1.0 uses a local process job manager and filesystem artifact store. It supports
non-streaming chat completions, a single two-stage fallback, and Python only. Pricing is static
configuration rather than provider billing data. Exact validators intentionally do not provide
semantic-equivalence scoring. There is no hosted Cloud/SaaS service, account system, traffic proxy,
browser UI, distributed worker system, learned routing, or model training.

## Roadmap (not available in 0.1.0)

Potential post-0.1 work includes richer request modalities, more provider-specific metadata,
scalable artifact-store adapters, and additional language SDKs. These are directions, not current
features or commitments.

## Development and documentation

For an editable development install:

```bash
python -m venv .venv
pip install -e ".[dev]"
pytest
ruff check .
ruff format --check .
```

Normal tests use fixtures and do not spend provider credits. Live provider testing is opt-in; run
it only explicitly, with the required credential configured and awareness of provider charges.

Detailed references:

- [Architecture](docs/architecture.md)
- [Serialized contracts](docs/contracts.md)
- [E0.5 real-world validation](docs/e0.5-real-world-validation.md)

## License

InferenceFit is licensed under the [Apache License 2.0](LICENSE) (`Apache-2.0`).
