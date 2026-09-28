# Examples

Run examples from a source checkout with InferenceFit 0.2.0 installed.

| Example | Purpose | Credential |
| --- | --- | --- |
| [Basic fixture workload](basic/eval.yaml) | Deterministic offline quick start and fallback | None |
| [Lead fixture workload](lead_semantic_units/eval.fixture.yaml) | Synthetic extraction with hidden expected units | None |
| [Multilingual fixtures](lead_semantic_units/eval.multilingual.fixture.yaml) | Offline multilingual coverage | None |
| [Fireworks smoke](lead_semantic_units/eval.fireworks.smoke.yaml) | Live chat completions | `FIREWORKS_API_KEY` |
| [DeepSeek smoke](lead_semantic_units/eval.deepseek.smoke.yaml) | Live chat completions | `DEEPSEEK_API_KEY` |
| [OpenRouter smoke](lead_semantic_units/eval.openrouter.smoke.yaml) | Live chat completions and request metadata | `OPEN_ROUTER_API_KEY` |
| [Gemini smoke](lead_semantic_units/eval.gemini.smoke.yaml) | Live OpenAI-compatible chat completions | `GEMINI_API_KEY` |
| [OpenAI smoke](lead_semantic_units/eval.openai.smoke.yaml) | Live stateless Responses API | `OPENAI_API_KEY` |

```bash
inferencefit validate examples/basic/eval.yaml
inferencefit benchmark examples/basic/eval.yaml
```

Live specs make network requests and can spend provider credits. Set the matching key, then
explicitly run `inferencefit benchmark` with that spec's path. All specs retain
`schema_version: "0.1"`. Model IDs and supported parameters vary by model and account;
review the defaults before running. See the [lead example guide](lead_semantic_units/README.md)
for larger Fireworks/DeepSeek workloads, validation semantics, and opt-in live pytest commands.
The [main README](../README.md#providers-and-credentials) documents minimal candidates and the
preserved Ollama, vLLM, and custom-compatible endpoint paths.
