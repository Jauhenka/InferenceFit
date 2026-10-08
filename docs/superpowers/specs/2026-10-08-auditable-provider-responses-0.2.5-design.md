# InferenceFit 0.2.5 Auditable Provider Responses

## Scope

PyPI already hosts 0.2.4, so this patch is 0.2.5. Preserve evaluation schema version `"0.1"`, existing candidate syntax, text, token totals, costs, retry, and error behavior. No billable requests, SDK additions, provider rewrite, publication, or tag creation.

## Contracts and persistence

Add nullable `raw_response`, `finish_reason`, `provider_finish_reason`, `provider_request_id`, `reasoning_tokens`, `reasoning_content`, and `usage_details` to `ProviderResponse` and `Observation`. The runner copies these on successful requests; the existing `Observation.model_dump_json()` JSONL path and `Observation.model_validate_json()` reload path persist them. Older records omit the fields and load as `None`. `ResultBundle` stays an aggregate; per-request native data lives in `observations.jsonl`.

Use a small shared provider metadata helper for conservative finish-reason mapping, valid nonnegative reasoning counts, safe native-body copying, and request-ID header extraction. Store JSON data returned by the provider, not request payloads or headers. Redact credential-bearing object keys and the resolved API key if echoed in otherwise native data. Never infer reasoning from answer text or subtract reasoning from total output tokens. `reasoning_content` contains only provider-exposed thinking or reasoning text. Unknown or missing metadata stays `None`.

## Providers

Anthropic reads `ANTHROPIC_WORKSPACE_ID` at request time and adds `anthropic-workspace-id` only when configured, for both registered names. Its `stop_reason` is preserved verbatim and mapped to common `stop`, `length`, `tool_calls`, `refusal`, or `pause` where known. `request-id` comes from the response header. Preserve all content blocks and native usage in the safe `raw_response` and `usage_details`; only actual `thinking` blocks contribute `reasoning_content`. Anthropic does not separately report reasoning token usage in the existing Messages response, so `reasoning_tokens` remains `None`.

The OpenAI Responses adapter and shared OpenAI-compatible chat adapter already parse response JSON. Enrich their `ProviderResponse` values without changing their request paths. OpenAI Responses reasoning counts come from `usage.output_tokens_details.reasoning_tokens`; exposed reasoning text/summary comes from reasoning output items. Chat-compatible responses (including Gemini, DeepSeek, and Fireworks) preserve `choices[0].finish_reason`, native usage, request IDs where exposed, and explicit `message.reasoning_content` or analogous returned fields when present. Unsupported provider-specific data remains in `raw_response`; no fabricated reasoning metrics.

## Verification

Mock HTTP for workspace presence/absence and both aliases, native stop reasons, request IDs, thinking/text blocks, missing reasoning, cache usage, chat/OpenAI enrichment, secret redaction, JSONL round trips, old-record loading, and public benchmark behavior. Run full pytest, Ruff, build, Twine, archive audit, and installed wheel/sdist smoke.
