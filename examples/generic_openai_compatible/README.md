# Generic OpenAI-compatible endpoint

This example calls any OpenAI-compatible chat-completions server through the canonical
`provider: custom` candidate. It uses only reserved placeholder names (`api.example.com`,
`some/model-name`, `example-main`); it never stores a real key, host, or model ID.

## Layout

- `cases.jsonl`: one synthetic sentiment-classification case with a hidden expected label.
- `eval.yaml`: a single `provider: custom` candidate, a schema routing gate, an exact
  label check, and a bounded execution envelope.

## The canonical candidate

```yaml
candidates:
  - id: generic-chat
    provider: custom
    model: some/model-name
    base_url: https://api.example.com/v1
    credential_ref: example-main
    parameters:
      max_tokens: 256
```

- `provider: custom` is the canonical way to target a server that speaks the OpenAI
  chat-completions protocol but has no first-class adapter. Prefer a first-class adapter
  (`openai`, `openrouter`, `gemini`, `deepseek`, or `fireworks`) when one exists, because it
  may encode provider-specific request and response details. Existing local `ollama` and
  `vllm` profiles also remain available.
- `base_url` is the explicit endpoint root. InferenceFit posts to
  `<base_url>/chat/completions`, so the path must not itself end in `chat/completions`.
  A trailing `/` is tolerated.
- `model` is the native model string the server expects; it is sent unchanged.
- `parameters` are forwarded to the request body. `max_tokens: 256` requests a bounded
  response where the target supports that parameter. `model`, `messages`, and `stream` are
  reserved; using them in `parameters` raises a configuration error before HTTP.

## Credentials

`credential_ref: example-main` is an opaque name. At run time it resolves to the
`INFERENCEFIT_CREDENTIAL_EXAMPLE_MAIN` environment variable (the reference is normalized to
upper case and joined with the `INFERENCEFIT_CREDENTIAL_` prefix). Set it in your shell or
secret manager before a live run:

```console
inferencefit benchmark examples/generic_openai_compatible/eval.yaml
```

An explicitly referenced variable that is missing raises an error, so a typo fails loudly.
The resolved variable value must not be written to specs, logs, errors, or artifacts. Omitting
`credential_ref` is how you reach a credentialless endpoint.

## Credentialless localhost variant

For a local server that needs no token, omit `credential_ref` and point at loopback:

```yaml
candidates:
  - id: local-chat
    provider: custom
    model: some/model-name
    base_url: http://127.0.0.1:8000/v1
    parameters:
      max_tokens: 256
```

No `Authorization` header is sent when `credential_ref` is omitted. Local HTTP also accepts
`http://localhost:8000/v1` and `http://[::1]:8000/v1`.

## Cost

This example omits pricing on purpose. The endpoint, model, and rates behind a generic
OpenAI-compatible server are unknown to this repository, so quoting a price would be a
false claim. When `pricing` is absent the cost of a run is unknown. Add
`pricing.input_per_million` and `pricing.output_per_million` only with rates you have
verified for that exact server and model.

## OpenAI-compatible differences

"OpenAI-compatible" is a loose claim. A given server may differ from OpenAI in:

- request parameters it accepts (for example `max_tokens` versus `max_output_tokens`, or
  whether `temperature` and `response_format` are honored);
- response shape details such as optional `usage` fields (`prompt_tokens`,
  `completion_tokens`, `total_tokens`), which may be absent or `null`;
- the model ID echoed back in the response `model` field, which may differ from the
  requested `model`.
- authentication scheme, which may be a bearer token, a custom header, or none. InferenceFit
  0.2.2 supports Bearer or credentialless generic requests, not custom headers.

Keep the schema gate strict so malformed or invented fields surface as failures instead
of silent mismatches.

## Deprecated backward compatibility

Historically you could pass an unknown provider name together with a `base_url`, and
InferenceFit would silently fall back to the OpenAI-compatible transport. In 0.2.2 that
form warns and is deprecated, retained only for backward compatibility. Write `provider: custom`
instead of an unknown provider name plus a `base_url`.

## Running

Validation does not open a network connection, so it succeeds without the credential set:

```console
inferencefit validate examples/generic_openai_compatible/eval.yaml
inferencefit benchmark examples/generic_openai_compatible/eval.yaml
```

Before benchmarking, replace the placeholder URL and model with a real endpoint and native
model ID supplied by your project or service documentation. The benchmark command sends the
case to that endpoint, may spend provider credits, and requires
`INFERENCEFIT_CREDENTIAL_EXAMPLE_MAIN` when the reference is present.
