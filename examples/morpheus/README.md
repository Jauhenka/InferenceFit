# Morpheus hosted gateway example

This profile uses the hosted OpenAI-compatible gateway at `https://api.mor.org/api/v1`, backed by
the Morpheus inference marketplace. InferenceFit reads `MORPHEUS_API_KEY` (or an explicit
`credential_ref` environment variable). Replace `<model-id>` in `eval.yaml` with an active native
ID from the authenticated [models endpoint](https://apidocs.mor.org/api-reference/models/list).
Check the [current prices](https://apidocs.mor.org/documentation/models/pricing) before a run:

```bash
inferencefit validate examples/morpheus/eval.yaml
inferencefit benchmark examples/morpheus/eval.yaml
```

The hosted gateway is a managed API path; this example does not create on-chain sessions or make
an end-to-end attestation claim. InferenceFit reports unknown cost unless you configure pricing.
The request is non-streaming and limited to one case, one repetition, and 32 output tokens.
