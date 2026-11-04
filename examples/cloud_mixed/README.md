# Mixed fixture and InferenceFit Cloud benchmark

This synthetic example exercises the normal `EvaluationSpec` 0.1 benchmark runner with one offline fixture and one hosted Cloud candidate. `REPLACE-WITH-CLOUD-CATALOG-ID` is a placeholder. Select an ID returned by your authorized Cloud service; do not infer an upstream provider or model from the ID.

Cloud M2 has no public signup or login command. A Cloud operator must provision an account and issue a development token. Set `INFERENCEFIT_CLOUD_TOKEN` in your environment, never in `eval.yaml` or a CLI argument. Set `INFERENCEFIT_CLOUD_API_URL=http://127.0.0.1:8000` for an authorized local gateway. A non-loopback HTTPS endpoint additionally requires the deliberately configured `INFERENCEFIT_CLOUD_TRUSTED_ORIGIN` to match it exactly. Treat that setting as an authorization to send both the token and workload data to that operator. No official production origin is assumed by this example.

Check the connection and server-owned catalog before editing the candidate:

```text
inferencefit cloud status
inferencefit cloud models
inferencefit cloud balance
inferencefit validate examples/cloud_mixed/eval.yaml
```

Review the hosted request count, token limit, data sensitivity, available credit, and the Cloud quote before authorizing a billable run. A quote is an estimate, not a spending ceiling. The offline fixture is useful for plumbing checks; it is not evidence that a hosted model is suitable. Once approved, run `inferencefit benchmark examples/cloud_mixed/eval.yaml` and inspect `observations.jsonl` and `result.json` in the run directory. Cloud observation cost is the settled customer charge when the status lookup succeeds; otherwise it is unknown. A cost constraint is applied after inference and does not prevent spending.
