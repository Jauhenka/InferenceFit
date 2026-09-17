# InferenceFit

InferenceFit is a local-first, workload-specific LLM benchmark and deterministic configuration optimizer. It evaluates your test cases against candidate providers/models, measures quality, reliability, latency, tokens, and cost, applies hard constraints, exposes the Pareto frontier, and emits an open routing recommendation.

There is no universally best model: there is a most effective configuration for a particular workload and set of constraints.

## Quick start

Requires Python 3.11 or newer.

```bash
python -m venv .venv
pip install -e ".[dev]"
inferencefit validate examples/basic/eval.yaml
inferencefit benchmark examples/basic/eval.yaml
```

The included example is deterministic, offline, and requires no API key. It compares a cheap fixture against a stronger fixture and evaluates a runtime-valid fallback cascade. Artifacts are written under `.inferencefit/runs/<run-id>/`.

Python uses the same core:

```python
import asyncio
from inferencefit import benchmark

result = asyncio.run(benchmark("examples/basic/eval.yaml"))
print(result.recommendation)
```

Start the local daemon with `inferencefit serve` (default `127.0.0.1:8787`). It exposes `GET /health`, `POST /v1/runs`, `GET /v1/runs/{id}`, `GET /v1/runs/{id}/result`, and `POST /v1/runs/{id}/cancel`.

## EvaluationSpec 0.1

An EvaluationSpec names a JSONL dataset, candidates, validators, hard constraints, an objective, and bounded execution settings. Candidate and validator IDs are unique. Supported objectives are `min_cost`, `min_latency`, `max_quality`, `max_reliability`, and `balanced`. The balanced-v1 heuristic is `0.45 quality + 0.30 inverse-normalized cost + 0.15 inverse-normalized p95 latency + 0.10 reliability`.

Candidate pricing is an explicit snapshot in USD per million input/output tokens. InferenceFit never fetches prices. Unknown token usage or pricing stays unknown, and a configuration becomes unrankable when the selected objective requires that unknown metric.

## Dataset and validators

Each JSONL line is a versionable test case with `id`, `request.messages`, arbitrary JSON `expected`, and arbitrary JSON-object `metadata`. The dataset hash is SHA-256 over canonical JSON records.

Built-in validators are `exact`, `regex`, `enum`, `json_schema`, `numeric`, `contains`, and local `python`. `target` and `reference` use RFC 6901 JSON Pointer. Exact, numeric, and Python validators depend on hidden evaluation ground truth and are eval-only. Regex, enum, JSON Schema, and fixed contains checks are runtime-capable and may be routing gates. Configuration rejects eval-only routing gates.

Local Python validators execute arbitrary local code with the current process permissions. They are not sandboxed; never use callables supplied by an untrusted remote party.

## Providers and credentials

`fixture` is deterministic and offline. The general non-streaming OpenAI-compatible adapter supports arbitrary endpoints plus OpenRouter, Fireworks, Ollama, and vLLM defaults without vendor SDKs.

Credentials are opaque references. For `credential_ref: fireworks-main`, resolution checks `INFERENCEFIT_CREDENTIAL_FIREWORKS_MAIN`, then the conventional provider fallback (`FIREWORKS_API_KEY` or `OPENROUTER_API_KEY`). Keys are not serialized, logged, or placed in error messages.

## Results and routing

Hard constraints include minimum end-to-end success, maximum p95 latency, provider error rate, and cost per 1,000 requests. Failed candidates remain visible but cannot be recommended. When none qualify, recommendation is null and the routing policy is explicitly non-routable.

Two-stage cascades fall back only on provider error or failure of a runtime-capable routing gate. They never use hidden expected answers as production routing signals. Simulation reuses existing observations and accounts for sequential cost and latency.

Every completed run contains:

- `manifest.json` — provenance, settings, lifecycle state;
- `spec.yaml` and `dataset.jsonl` — exact input snapshots;
- `observations.jsonl` — one flushed terminal record per planned unit;
- `result.json` — complete metrics, constraints, Pareto, and ranking;
- `summary.md` — human-readable projection of the result;
- `routing-policy.yaml` — single/fallback policy or explicit non-routable result.

Resume with `inferencefit benchmark eval.yaml --resume <run-id>`. Compatibility hashes are checked and completed `(case, candidate, repetition)` identities are skipped.

## Development

```bash
pytest
ruff check .
ruff format --check .
```

Normal tests and CI use fixtures and never spend provider credits. Live provider testing is intentionally opt-in and should be gated with `INFERENCEFIT_LIVE_TESTS=1`.

## Security and E0 limits

Datasets and outputs remain on the local filesystem. Raw prompts/responses are not logged at INFO. The daemon binds only to localhost and has no authentication, so it is not a network service. E0 has a local process job manager, filesystem storage, non-streaming chat completions, and a simple two-stage cascade. It does not include Cloud/SaaS, accounts, distributed workers, a traffic proxy, browser UI, learned routing, training, or SDKs for other languages.

Sensible E1 work includes richer request modalities, more provider-specific metadata, scalable artifact-store adapters, and additional language SDKs built from the versioned contracts.

See [architecture](docs/architecture.md) and [contracts](docs/contracts.md).

## License

Apache-2.0.
