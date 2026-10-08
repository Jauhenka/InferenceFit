# Native Anthropic (Claude) 0.2.4 Design

## Intent and boundary

InferenceFit 0.2.4 makes an existing Claude workload usable through the ordinary `EvaluationSpec`, `benchmark()`, CLI, observations, and release artifacts. `anthropic` is canonical; `claude` is a user-facing alias. Native model IDs are opaque passthrough strings. No model registry, model-only inference, new CLI discovery command, SDK dependency, streaming, tool loop, or change to other providers is added. Serialized `schema_version: "0.1"` stays unchanged.

The repository has no name-normalization or model-inference layer. Both exact lowercase names are registered in the existing factory and resolve the same `AnthropicProvider` class and `ANTHROPIC_API_KEY` fallback. The candidate spec retains the user's provider spelling; successful native observations use canonical `provider: anthropic`. Other providers remain case-sensitive. Existing explicit `base_url` precedence is preserved: a named provider with an explicit URL uses the generic OpenAI-compatible route, as it already does for `openai` and `openrouter`.

## Native request and response

Use the existing `httpx` core dependency to POST non-streaming JSON to `https://api.anthropic.com/v1/messages` with `x-api-key` and `anthropic-version: 2023-06-01`. This avoids an SDK dependency and its automatic retries, which would silently multiply the engine's retry policy. The [official Messages API](https://platform.claude.com/docs/en/api/messages/create) requires `model`, `messages`, and `max_tokens`. Default `max_tokens` to 1024 when absent; accept `parameters.max_tokens` and one `max_output_tokens` alias, rejecting conflicting values before HTTP. Pass through other supported parameters, including explicitly supplied `temperature`, without inventing a temperature default. Current Claude models may reject temperatures other than 1.0, so users must check model support.

Move only leading `system` messages to Anthropic's top-level `system` field, joining multiple instructions with two newlines. Preserve `user` and `assistant` message order and text. Reject a system message after conversation has started, a message `name`, or a request with no user/assistant messages before HTTP rather than silently changing semantics. Reserve `model`, `messages`, `system`, and `stream` in candidate parameters. The shared engine still enforces its configured request timeout and retry limits.

Extract and concatenate response blocks whose `type` is `text`; ignore non-text blocks and treat no usable text or malformed structure as a safe response error. Preserve the response's model ID when valid, otherwise the requested ID. Normalize nonnegative `usage.input_tokens` plus optional cache-creation/read tokens as total input tokens, nonnegative `usage.output_tokens` as output, and compute total when both are known. Cached tokens can have different billing rates; generic configured pricing is only a simple estimate, never an invoice. Without configured pricing, cost stays unknown. Never copy response bodies, provider exceptions, or resolved credentials into errors or artifacts.

Classify HTTP failures with the shared error helper. 401/403 are nonretryable, 429/5xx (including Anthropic 529) follow existing bounded retry policy, and timeouts/network failures use the existing safe kinds. No SDK or adapter-level retries.

## Discovery, examples, and release

Prominently enumerate **Anthropic (Claude)** in README/provider tables, portable Agent Skill, example index, and 0.2.4 release notes. Show canonical `provider: anthropic`, mention accepted `provider: claude`, the `ANTHROPIC_API_KEY` fallback, native model IDs, model-specific parameter limits, and an offline-valid example with a replaceable `<claude-model-id>` placeholder. No hardcoded closed model list. Model-only inference remains absent; a candidate must specify its provider.

Tests cover alias dispatch and credential precedence, request mapping, response usage and model normalization, safe errors and retry taxonomy, a public benchmark through both names, secret safety, release metadata, and installed-distribution smoke. Existing provider, custom, fixture, preset, API, and resume tests remain unchanged. Publishing and tagging remain human-controlled.
