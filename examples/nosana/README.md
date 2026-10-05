# Nosana hosted LLM inference example

Nosana serves an OpenAI-compatible LLM API at `https://inference.nosana.com/v1` over its GPU
infrastructure. InferenceFit reads `NOSANA_API_KEY` (or an explicit `credential_ref` environment
variable). The authenticated [models endpoint](https://learn.nosana.com/api/llm.html#list-models)
lists only models currently served. Replace `<model-id>` in `eval.yaml` with one of those IDs:

```bash
inferencefit validate examples/nosana/eval.yaml
inferencefit benchmark examples/nosana/eval.yaml
```

Availability and prices change. InferenceFit does not query the billing history to assign request
cost; add explicit `pricing` if desired, otherwise cost remains unknown. The request is
non-streaming and limited to one case, one repetition, and 32 output tokens.
