# Anthropic (Claude) example

Set `ANTHROPIC_API_KEY`, replace `<claude-model-id>` in `eval.yaml` with a model ID currently
available to your account, and run:

For a multi-workspace key, also set `ANTHROPIC_WORKSPACE_ID`; the native adapter sends it as
`anthropic-workspace-id`. Leave it unset for a single-workspace key. Do not put the key or workspace
ID in the spec.

```bash
inferencefit validate examples/anthropic/eval.yaml
inferencefit benchmark examples/anthropic/eval.yaml
```

`provider: anthropic` selects the native Anthropic Messages API; `provider: claude` is an alias.
Use the provider name explicitly. A model ID alone does not choose a provider. The example makes
one non-streaming request with at most 64 output tokens. It can spend credits. Check current model
availability and pricing before running. Monetary cost remains unknown unless you configure
`pricing` with complete token usage; configured prices are estimates, especially for cached tokens.
