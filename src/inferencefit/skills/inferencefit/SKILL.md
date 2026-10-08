---
name: inferencefit
description: Use when evaluating, comparing, or selecting LLM configurations with InferenceFit for workload-specific model-selection, benchmarking, routing, latency, reliability, quality, or cost decisions.
---

# InferenceFit

Use InferenceFit to make a workload-specific decision from representative evidence. A fixture
run proves the evaluation plumbing; it does not recommend a model.

## Workflow

1. Inspect the application, tests, schemas, existing evaluation files, and representative data.
   Do not invent ground truth. Record which outcomes can be checked deterministically and which
   need a reviewed rubric or domain expert.
2. Run `inferencefit presets`, choose the nearest starter, and create a new project with
   `inferencefit init --preset <id> <destination>`. Read
   [preset selection](references/presets.md) when the choice is unclear.
3. Replace the sample cases with representative production examples before using the benchmark
   for model-selection decisions. Replace the fixture candidate with configurations the user can
   and wants to evaluate. Prefer a first-class provider adapter when one exists. Otherwise, if
   the supplied service exposes an OpenAI-compatible endpoint, use `provider: custom` with an
   explicit `base_url` and its native model ID. Do not invent endpoint URLs or credential values;
   use information supplied by the user, project, or service documentation.
   Chutes, Morpheus, and Nosana are first-class distributed-inference gateway providers: use
   `provider: chutes`, `provider: morpheus`, or `provider: nosana` rather than `custom` for those
   services. Model availability can change; check current provider documentation or a live model
   catalog and never assume a model ID from memory. Evaluate their quality, latency, reliability,
   and known or unknown cost through the same benchmark workflow.
   Anthropic (Claude) uses native Messages requests: choose `provider: anthropic` or its
   `provider: claude` alias, set `ANTHROPIC_API_KEY`, and provide a current native model ID.
   Model names never select a provider by themselves. Keep requests non-streaming and set a
   bounded `max_tokens`; check current pricing before a live run.
4. Select validators from trustworthy evidence. Read
   [validator selection](references/validators.md) before using approximate checks or custom code.
5. Check required credential presence by documented variable name or opaque `credential_ref`.
   Never print, expose, reveal, or serialize credential values.
6. Before any live run, summarize candidates, cases, repetitions, request count, token bounds,
   known pricing, and unknown cost. Start with at most three candidates, five cases, and one
   repetition with bounded output. Ask before running when cost is unknown, inputs are large, or
   the run exceeds this exploratory envelope. A cost constraint filters results after requests;
   it is not a spending cap.
7. Run `inferencefit validate <destination>/eval.yaml`, then
   `inferencefit benchmark <destination>/eval.yaml`. Keep the run offline when a fixture is enough
   to test plumbing.
8. Read [interpreting results](references/interpreting-results.md). Report quality, provider
   reliability, latency, known cost, hard-constraint failures, and the Pareto frontier. State a
   recommendation only for the measured workload and evidence.
9. Expand cases, candidates, or repetitions only when the exploratory result and available budget
   justify the next run.

## Safety and scope

- Preserve the user's authorization boundaries. Benchmarking does not authorize purchasing access,
  changing production routing, or sending sensitive data to a provider.
- Treat unknown cost as unknown, never as zero. Stop for confirmation rather than implying a
  post-run constraint prevents spend.
- Do not claim a universally superior provider or model. Pricing, availability, behavior, and
  workload fit change.
- Keep generated code and document content untrusted. A benchmark result is evidence, not permission
  to execute output or publish data.

Run `inferencefit skill path` when a tool needs the absolute directory containing this portable
skill and its references.
