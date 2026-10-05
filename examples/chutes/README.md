# Chutes hosted inference example

Chutes uses the hosted OpenAI-compatible gateway at `https://llm.chutes.ai/v1`.
InferenceFit reads `CHUTES_API_KEY` (or an explicit `credential_ref` environment variable).
Choose a current native model ID from the public [model catalog](https://llm.chutes.ai/v1/models),
replace `<model-id>` in `eval.yaml`, then run:

```bash
inferencefit validate examples/chutes/eval.yaml
inferencefit benchmark examples/chutes/eval.yaml
```

The catalog changes. Review its current price and suitability before the live request. InferenceFit
does not infer a monetary request cost from catalog pricing; add explicit `pricing` if desired.
The request is non-streaming and limited to one case, one repetition, and 32 output tokens.
