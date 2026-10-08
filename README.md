# InferenceFit

InferenceFit is a local-first toolkit for evaluating and selecting LLM configurations for a
specific workload. Instead of asking which model is universally "best," it runs your versioned
test cases against candidate providers and models, measures quality, reliability, latency, token
use, and cost, applies your hard constraints, and produces a deterministic recommendation and an
open routing policy.

InferenceFit 0.2.5 is a pre-1.0 release. Public APIs and serialized schemas may change before 1.0.

## Installation

InferenceFit requires Python 3.11 or newer.

```bash
pip install inferencefit
```

## Workload preset quick start

Discover the three built-in workload shapes and initialize the closest one:

```bash
inferencefit presets
inferencefit init --preset structured-extraction ./eval
inferencefit validate ./eval/eval.yaml
inferencefit benchmark ./eval/eval.yaml
```

The stable preset IDs are `coding`, `document-processing`, and `structured-extraction`. Each
generated project contains two synthetic cases and a deterministic offline fixture candidate, so
the first benchmark checks installation and evaluation plumbing without credentials or network
requests.

Replace the sample cases with representative production examples before using the benchmark for
model-selection decisions. Replace the fixture candidate with configurations you actually want to
evaluate, then review validators, constraints, pricing, and execution limits. Initialization never
overwrites an existing destination.

## Agent Skill

InferenceFit 0.2.5 also packages a portable Agent Skill for agents that prepare or interpret
workload-specific evaluations. Locate it with:

```bash
inferencefit skill path
```

Copy or link the printed `inferencefit` directory into a skills directory supported by your agent,
following that agent's own installation instructions. There is deliberately no universal skill
installer in this release. The Agent Skill is another frontend over the same core workflow used by
the CLI, Python API, and local daemon; it does not introduce a separate benchmark engine.

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

# Requires OPEN_ROUTER_API_KEY
inferencefit benchmark examples/lead_semantic_units/eval.openrouter.smoke.yaml

# Requires GEMINI_API_KEY
inferencefit benchmark examples/lead_semantic_units/eval.gemini.smoke.yaml

# Requires OPENAI_API_KEY
inferencefit benchmark examples/lead_semantic_units/eval.openai.smoke.yaml

# Replace <model-id> in each spec with a current native model ID first.
# Requires CHUTES_API_KEY
inferencefit benchmark examples/chutes/eval.yaml

# Requires MORPHEUS_API_KEY
inferencefit benchmark examples/morpheus/eval.yaml

# Requires NOSANA_API_KEY
inferencefit benchmark examples/nosana/eval.yaml

# Replace <claude-model-id> with an available Anthropic model ID first.
# Requires ANTHROPIC_API_KEY
inferencefit benchmark examples/anthropic/eval.yaml
```

The lead-semantic-units smoke specs use synthetic lead-extraction cases; the hosted-provider
examples use one small prompt each. See the
[example guide](examples/lead_semantic_units/README.md) and the
[E0.5 validation report](docs/e0.5-real-world-validation.md) for their contract, pricing snapshots,
and observed results.

## How evaluation works

An `EvaluationSpec` YAML file connects a JSONL dataset to candidates, validators, hard constraints,
an optimization objective, and bounded execution settings. Candidate pricing is an explicit
snapshot in USD per million input and output tokens; InferenceFit does not fetch price catalogs.
An authoritative per-request cost reported by OpenRouter takes precedence over configured pricing.
When neither reported cost nor sufficient token counts and pricing are available, cost is unknown.

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

The supported paths use non-streaming HTTP requests without vendor SDKs:

| Provider | API path | Default credential environment variable |
| --- | --- | --- |
| Fireworks (`fireworks`) | OpenAI-compatible chat completions | `FIREWORKS_API_KEY` |
| DeepSeek (`deepseek`) | OpenAI-compatible chat completions | `DEEPSEEK_API_KEY` |
| OpenRouter (`openrouter`) | Chat completions with reported cost and backend metadata | `OPEN_ROUTER_API_KEY` |
| Gemini (`gemini`) | Google's OpenAI-compatible chat completions endpoint | `GEMINI_API_KEY` |
| OpenAI (`openai`) | Native Responses API with `store: false` | `OPENAI_API_KEY` |
| Anthropic (`anthropic`, alias `claude`) | Native non-streaming Messages API | `ANTHROPIC_API_KEY` |
| Chutes (`chutes`) | Hosted OpenAI-compatible Chutes inference gateway | `CHUTES_API_KEY` |
| Morpheus (`morpheus`) | Hosted OpenAI-compatible Morpheus gateway | `MORPHEUS_API_KEY` |
| Nosana (`nosana`) | Hosted OpenAI-compatible LLM inference | `NOSANA_API_KEY` |
| Fixture (`fixture`) | Deterministic offline testing | None |
| Ollama (`ollama`) and vLLM (`vllm`) | Local OpenAI-compatible chat completions | Optional explicit reference |
| Generic OpenAI-compatible (`custom`) | Chat completions at an explicit `base_url` | Optional explicit reference |

Credentials are resolved from opaque references. For example, `credential_ref: fireworks-main`
checks `INFERENCEFIT_CREDENTIAL_FIREWORKS_MAIN` first, then `FIREWORKS_API_KEY`. The other hosted
providers fall back to their variables in the table. OpenRouter's exact name is
`OPEN_ROUTER_API_KEY`; the older `OPENROUTER_API_KEY` spelling is not a resolver fallback.
Credential values are never written to run artifacts.

### Anthropic (Claude)

Use `provider: anthropic` for native Anthropic Messages requests. `provider: claude` is an accepted
alias for the same adapter; the observation reports canonical `anthropic`. The provider must be
explicit because model IDs are opaque and never used to infer a provider. `ANTHROPIC_API_KEY` is
the fallback after an optional opaque `credential_ref`. The adapter sends leading system messages
as a top-level system prompt and preserves the user/assistant conversation order. System messages
after conversation starts and named messages fail before HTTP.

```yaml
candidates:
  - id: claude
    provider: anthropic
    model: <claude-model-id>
    parameters: {max_tokens: 64}
```

Replace the placeholder with a currently available Anthropic model ID. `max_tokens` defaults to
1024 if omitted; `max_output_tokens` is also accepted as an alias. `temperature` is sent only when
configured because support varies by model. `model`, `messages`, `system`, and `stream` are reserved
parameters; streaming is unsupported. The native response's text, returned model, and available
token usage enter the usual benchmark artifacts. Cost stays unknown without configured `pricing`
and complete usage. Static pricing is only an estimate and does not account for cache-specific
rates. See the [Anthropic example](examples/anthropic/README.md). An explicit `base_url` retains
the existing generic chat-completions override, so omit it for the native Messages API.

For a multi-workspace key, set `ANTHROPIC_WORKSPACE_ID`. The native adapter sends its value as
`anthropic-workspace-id` for both `provider: anthropic` and `provider: claude`. Leave it unset for
a single-workspace key. The workspace header and API key are never copied into artifacts.

### Provider-native audit data

Each successful `observations.jsonl` row can include optional `raw_response`,
`finish_reason`, `provider_finish_reason`, `provider_request_id`, `reasoning_tokens`,
`reasoning_content`, and `usage_details`. The native JSON retains returned content blocks and
usage, with credentials redacted. Only reasoning actually exposed by the API is recorded;
missing fields are `null`. `usage.output_tokens` remains total provider output, including any
reasoning tokens the provider counts. The aggregate `result.json` remains a summary. Existing
schema version `"0.1"` observations continue to load. See [serialized contracts](docs/contracts.md)
for field semantics and the 0.2.5 provider coverage.

### Decentralized inference providers

The `chutes`, `morpheus`, and `nosana` identifiers select hosted OpenAI-compatible gateways backed
by distributed inference infrastructure. They use the same benchmark workflow, shared adapter,
Bearer credential handling, and artifact format as other chat providers. Set the matching key in
the table, choose a **current native model ID**, and write `provider: chutes`, `provider:
morpheus`, or `provider: nosana` with no `base_url`. The [Chutes](examples/chutes/README.md),
[Morpheus](examples/morpheus/README.md), and [Nosana](examples/nosana/README.md) examples contain
one bounded request each; replace `<model-id>` after checking the provider's current catalog.

Chutes uses `https://llm.chutes.ai/v1`, whose public `/models` catalog changes. Morpheus uses the
managed `https://api.mor.org/api/v1` gateway backed by its inference marketplace; this gateway is
not an end-to-end attestation guarantee. Nosana uses `https://inference.nosana.com/v1`, whose
authenticated `/models` list contains models currently served. The named integrations do not
automatically discover models or prices during a benchmark. Configure `pricing` when you have a
current rate and need an estimate; otherwise monetary cost remains unknown. An explicit `base_url`
still overrides a named profile through the existing shared chat path. The adapter remains
non-streaming and rejects `parameters.stream` before HTTP.

Minimal candidate configurations for the existing hosted providers can be placed under
`candidates` in an evaluation spec with `schema_version: "0.1"` and a dataset of chat messages:

```yaml
candidates:
  - id: router
    provider: openrouter
    model: openrouter/free
    credential_ref: openrouter-main
    parameters: {max_tokens: 32}
  - id: gemini
    provider: gemini
    model: gemini-3.5-flash-lite
    credential_ref: gemini-main
    parameters: {max_tokens: 32}
  - id: openai
    provider: openai
    model: gpt-6-luna
    credential_ref: openai-main
    parameters: {max_output_tokens: 64}
```

These are the bundled smoke defaults, not a guarantee of model availability. Model IDs and
supported parameters vary by model and account; consult the provider's current documentation.
For example, some OpenAI models reject `temperature`. OpenAI normalizes `max_tokens` or
`max_completion_tokens` to `max_output_tokens`, rejects conflicting limits, and reserves
`model`, `input`, and `store`. Each evaluation is stateless. An explicit `base_url` selects
generic chat completions, including when overriding a hosted provider's native path.

For an otherwise OpenAI-compatible endpoint, use the canonical `provider: custom` with an
explicit API `base_url` and the server's native model ID:

```yaml
candidates:
  - id: my-endpoint
    provider: custom
    model: some/model-name
    base_url: https://api.example.com/v1
    credential_ref: example-main
    parameters: {max_tokens: 64}
```

`credential_ref: example-main` reads `INFERENCEFIT_CREDENTIAL_EXAMPLE_MAIN`; omit the reference
for a credentialless local endpoint such as `http://127.0.0.1:8000/v1` or
`http://[::1]:8000/v1`. The base URL is an API root, not a full `/chat/completions` URL;
InferenceFit appends that path. Use HTTPS for remote endpoints. `model`, `messages`, and `stream`
are reserved request parameters, and custom headers are not supported. OpenAI-compatible servers
vary in accepted parameters and response details, so verify the endpoint and credential setup
from your project or provider documentation before sending data. Do not put secrets in URLs or
parameters: those values are persisted in run artifacts. Cost is unknown unless complete token
usage and configured `pricing` are available; unknown cost is not zero.

Prefer a first-class provider adapter when one exists because it may normalize provider-specific
behavior, metadata, or cost. For a local endpoint with a built-in profile, `provider: ollama` and
`provider: vllm` remain available. An unknown provider name plus explicit `base_url` continues to
run for backward compatibility, but that path is deprecated and warns since 0.2.2. New
configurations must use `provider: custom`. See the
[generic example](examples/generic_openai_compatible/README.md) and
[examples guide](examples/README.md).

## Local daemon

```bash
inferencefit serve
```

The daemon defaults to `127.0.0.1:8787` and exposes health, run creation, status, result, and
cancellation endpoints. It has no authentication and is intended only for trusted localhost use;
do not expose it to a network.

## Current limitations

Version 0.2.5 uses a local process job manager and filesystem artifact store. It supports
non-streaming chat completions, OpenAI Responses text output, and Anthropic Messages text output,
a single two-stage fallback,
and Python only. Cost uses reported request cost where available, then static configured prices;
it is not an invoice reconciliation system. Exact validators intentionally do not provide
semantic-equivalence scoring. There is no hosted Cloud/SaaS service, account system, traffic proxy,
browser UI, distributed worker system, learned routing, or model training.

## Roadmap (not available in 0.2.5)

Potential future work includes richer request modalities, more provider-specific metadata,
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

```bash
python -m pytest tests/test_provider_live.py -m provider_live -q
```

Each live check skips when its own key is absent. To override the bundled model defaults, set
`OPEN_ROUTER_TEST_MODEL`, `GEMINI_TEST_MODEL`, or `OPENAI_TEST_MODEL` for the matching provider.
The decentralized gateway checks use `CHUTES_TEST_MODEL`, `MORPHEUS_TEST_MODEL`, or
`NOSANA_TEST_MODEL`. Chutes can select an inexpensive text model from one public `/models` read.
Morpheus requires an explicit `MORPHEUS_TEST_MODEL` because its active-model catalog does not
provide machine-readable prices. Nosana requires an explicit `NOSANA_TEST_MODEL`; its authenticated
catalog confirms that the selected ID is currently served, but does not reliably distinguish
chat-ready models from embedding or reasoning-only responses.
Ordinary CI supplies no credentials and runs the offline suite.

Detailed references:

- [Architecture](docs/architecture.md)
- [Serialized contracts](docs/contracts.md)
- [0.2.5 release notes](docs/releases/0.2.5.md)
- [0.2.4 release notes](docs/releases/0.2.4.md)
- [0.2.3 release notes](docs/releases/0.2.3.md)
- [0.2.2 release notes](docs/releases/0.2.2.md)
- [0.2.1 release notes](docs/releases/0.2.1.md)
- [0.2.0 release notes](docs/releases/0.2.0.md)
- [0.1.0 release notes](docs/releases/0.1.0.md)
- [E0.5 real-world validation](docs/e0.5-real-world-validation.md)

## License

InferenceFit is licensed under the [Apache License 2.0](LICENSE) (`Apache-2.0`).
