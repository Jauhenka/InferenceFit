# Changelog

All notable changes to InferenceFit are documented in this file.

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
