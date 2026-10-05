# Preset selection

Use `inferencefit presets` to see the installed registry, then initialize the closest starting
shape with `inferencefit init --preset <id> <destination>`.

## Built-in choices

- `coding`: code generation or transformation where schemas, exact fields, unit tests, or trusted
  local checks can measure correctness. Never blindly execute generated output.
- `document-processing`: starts as short document classification. QA, summarization, synthesis,
  and long-input work require their own representative cases and quality rubric.
- `structured-extraction`: typed JSON extraction where a schema and expected fields define the
  contract. Prefer field-level checks when whole-object equality is unnecessarily strict.

Each project is intentionally small: two synthetic cases and one offline fixture candidate. First
run it unchanged to check plumbing. Then customize the cases, candidates, validators, constraints,
and execution settings for the real workload. No preset supplies current provider rankings or a
selection-grade dataset.

If no preset fits, adapt a normal schema-version `0.1` evaluation rather than forcing the workload
into the wrong shape. Use `inferencefit validate <path>/eval.yaml` after every structural change.

When replacing a fixture candidate, prefer a first-class provider adapter. For an otherwise
OpenAI-compatible endpoint, use `provider: custom`, the supplied API `base_url`, the native model
ID, and an opaque `credential_ref` if Bearer authentication is required. A credentialless local
endpoint can omit the reference. Do not invent an endpoint URL or expose a credential value.
Unknown cost remains unknown until pricing and token usage are available.
