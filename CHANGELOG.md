# Changelog

All notable changes to InferenceFit are documented in this file.

## 0.2.0

Multi-provider evaluation release.

- Add OpenRouter chat completions with authoritative request cost and backend metadata,
  Gemini through its OpenAI-compatible endpoint, and stateless OpenAI Responses requests
  with `store: false` and normalized output-token limits.
- Preserve Fireworks, DeepSeek, offline fixtures, Ollama/vLLM, and explicit custom-compatible
  endpoints. Resolve the new live credentials as `OPEN_ROUTER_API_KEY`, `GEMINI_API_KEY`,
  and `OPENAI_API_KEY` after any configured opaque credential reference.
- Persist optional observation `provider_backend` and `cost_source` fields. Prefer valid
  provider-reported cost, then configured pricing; preserve unknown usage and cost.
- Keep serialized `schema_version: "0.1"`; older observations remain readable and resumable.
- Provide offline mocked-provider coverage and opt-in live smoke specs and tests.
- Coordinate package, API, manifest, CI, and TestPyPI release versions at 0.2.0 and extend
  distribution secret scanning for the exact new credential names.

## 0.1.0

Initial public release.

- Evaluate LLM configurations against workload-specific, file-based datasets and
  `EvaluationSpec` files.
- Use the deterministic offline fixture provider or the non-streaming OpenAI-compatible
  provider architecture. Fireworks and DeepSeek integrations have been validated against
  their real APIs.
- Score responses with declarative exact, regular-expression, enum, JSON Schema, numeric,
  contains, and local Python validators.
- Measure quality, cost, latency, and reliability, then apply hard constraints and expose the
  Pareto frontier.
- Select eligible configurations with deterministic optimization objectives, including a
  documented balanced heuristic.
- Produce a runtime-valid two-stage fallback cascade that reacts only to provider errors and
  runtime-capable validation gates.
- Persist resumable filesystem runs with provenance, observations, result summaries, and an
  open `routing-policy.yaml` artifact.
- Run the same benchmark core through the `inferencefit` CLI, the async Python API, or a local
  FastAPI daemon.
