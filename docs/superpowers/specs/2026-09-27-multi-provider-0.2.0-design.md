# Multi-Provider 0.2.0 Design

## Intent and success criteria

InferenceFit 0.2.0 establishes and validates the provider abstraction with three new first-class
providers: OpenRouter, Gemini, and OpenAI. Each must work through the existing public
`benchmark()` path, normalized observation/result contracts, retry and timeout behavior, artifact
pipeline, CLI, and HTTP API without introducing vendor logic into benchmark orchestration.

Existing Fireworks, DeepSeek, Ollama/vLLM presets, fixture, and custom OpenAI-compatible behavior
must remain intact.
The release stays deliberately small: it adds only the provider-specific boundaries needed to
exercise meaningfully different APIs and makes the smallest central construction cleanup needed
to keep them isolated.

Success means a user can select `provider: openrouter`, `provider: gemini`, or `provider: openai`
with native model identifiers; credentials resolve from `OPEN_ROUTER_API_KEY`, `GEMINI_API_KEY`,
or `OPENAI_API_KEY`; offline tests cover each adapter; and opt-in live tests independently run a
tiny workload through the complete benchmark/artifact path when the corresponding key exists.

## Scope and non-goals

The supported provider set after 0.2.0 is Fireworks, DeepSeek, OpenRouter, Gemini, OpenAI, custom
OpenAI-compatible endpoints, the existing Ollama/vLLM local-compatible presets, and the fixture
provider. Ollama and vLLM are preserved existing presets, not new first-class integrations in this
release. No other provider integration is added.

Anthropic/Claude, Groq, Mistral, Lightchain/LCAI, additional provider integrations, InferenceFit
Cloud, user authentication, billing/credits/payments, hosted InferenceFit API keys, UI work, and a
dynamic plugin or provider-capability framework remain out of scope. The release does not add
OpenRouter routing policy, model cascades beyond existing InferenceFit behavior, Gemini-native
tools, OpenAI-hosted tools, streaming, or stateful conversations.

## Architecture decision

Use a hybrid design with one shared contract and three deliberately small provider boundaries:

1. `OpenAICompatibleProvider` remains the shared non-streaming chat-completions transport for
   Fireworks, DeepSeek, Ollama/vLLM, custom endpoints, and Gemini. Gemini is a first-class profile:
   a documented preset URL, exact credential fallback, central factory entry, focused tests,
   examples, and live verification. It does not need a duplicate adapter because Google's
   supported compatibility endpoint already uses Bearer authentication and the chat-completions
   request/response shape.
2. `OpenRouterProvider` specializes the compatible transport only for metadata opt-in and
   OpenRouter-specific cost/backend normalization.
3. `OpenAIResponsesProvider` is a focused adapter for `POST /v1/responses`. OpenAI recommends the
   Responses API for new integrations, and its `input` plus typed `output` shape differs enough
   from chat completions that treating it as a URL preset would obscure real translation logic.

A small `providers.registry.create_provider(...)` function centralizes built-in construction.
It uses a static mapping for the three specialized/profiled providers, handles fixture setup in
one place, and falls back to `OpenAICompatibleProvider` for the existing Fireworks, DeepSeek, and
local/custom-compatible path. An explicit candidate `base_url` takes precedence over a built-in
provider name and selects the generic compatible adapter, preserving the current custom-endpoint
escape hatch. This is a fixed release registry, not a plugin system. `core.benchmark()` loads data
and orchestrates work but no longer knows provider class names or vendor branches.

Alternatives rejected:

- Making all three providers generic presets would be smallest in lines but would lose
  OpenRouter metadata/cost and mishandle OpenAI Responses payload/output semantics.
- Giving every provider a fully separate HTTP implementation would duplicate request, latency,
  token, and error handling and create unnecessary drift.
- Building a dynamic plugin/capability system would exceed the validated needs of 0.2.0.

## Normalized provider and observation contracts

`ProviderResponse` gains optional total tokens, provider-reported cost, and upstream backend data;
the existing provider and actual-model fields become part of the persisted flow instead of being
dropped. `TokenUsage` gains optional `total_tokens`. `Observation` gains optional `provider`,
`model`, `provider_backend`, and `cost_source` fields. Every new serialized field is optional or
defaulted so existing 0.1-shaped observations remain readable; `schema_version` remains `0.1`.

The runner applies one cost rule for every provider:

1. use a provider-reported monetary request cost, including a valid zero, and label it
   `provider_reported`;
2. otherwise calculate from explicitly configured per-million-token pricing and label it
   `configured_pricing`;
3. otherwise leave cost and provenance unknown.

No adapter guesses pricing. Missing optional usage, model, cost, or backend metadata never turns a
successful text response into a failure.

## Shared HTTP and error behavior

The compatible and Responses transports share a small secret-safe HTTP error normalizer. It uses
HTTP status and, where needed, a machine-readable error code; it never copies response bodies,
headers, prompts, or credentials into exceptions. Authentication/permission and ordinary client
errors are non-retryable. Network failures, timeouts, rate limits, and transient server/provider
failures are retryable according to the existing runner's bounded retry policy. Provider-specific
machine codes may refine retryability only when official semantics distinguish a temporary limit
from a quota or spend condition; this classification does not add billing functionality.

The existing runner remains the sole owner of total request timeout, attempt count, backoff, and
terminal error observations.

## Provider flows

### OpenRouter

`OpenRouterProvider` posts the existing messages and candidate parameters to
`https://openrouter.ai/api/v1/chat/completions`, preserves native IDs such as
`openrouter/free` or `provider/model-name`, and opts into `X-OpenRouter-Metadata: enabled`. It
normalizes response text, prompt/completion/total tokens, actual model, authoritative
`usage.cost`, and the selected upstream provider when present. Routing metadata and cost remain
optional.

The 0.1.0 generic preset used the incorrect fallback spelling `OPENROUTER_API_KEY`. Version 0.2.0
intentionally replaces it with the required `OPEN_ROUTER_API_KEY` and does not retain the legacy
alias.

### Gemini

Gemini uses the officially documented compatibility base URL, stored canonically as
`https://generativelanguage.googleapis.com/v1beta/openai` with the shared chat-completions
transport and `GEMINI_API_KEY`. Native model names are preserved. The adapter normalizes the
OpenAI-shaped text, usage, and actual model fields and otherwise relies on the shared error path.
Model-specific parameter support is not generalized or promised; unsupported parameters remain
safe non-retryable provider errors.

### OpenAI

`OpenAIResponsesProvider` posts to `https://api.openai.com/v1/responses` using `OPENAI_API_KEY`.
It maps the benchmark message array to Responses `input`, sends `store: false` because 0.2.0 is a
stateless local benchmark, and accepts native Responses parameters. For compatibility with
existing candidate specs, exactly one of `max_tokens` or `max_completion_tokens` may be translated
to `max_output_tokens` when the native field is absent; conflicting aliases fail as a secret-safe,
non-retryable configuration error. The adapter reserves `model`, `input`, and `store`; attempts to
override them through `candidate.parameters` fail before HTTP. Every other parameter is forwarded
unchanged after token-limit normalization, so native Responses parameters work and unsupported
chat-only parameters receive the provider's normal non-retryable client error. No other field is
silently dropped or rewritten.

Text extraction walks typed `output` items and concatenates `output_text` content in order rather
than assuming the first output item is a message. The adapter normalizes input/output/total tokens
and actual model. The current official Responses schema exposes token usage but not authoritative
per-request monetary cost, so OpenAI cost remains unknown unless the candidate supplies explicit
pricing for the existing configured-pricing fallback.

The native Responses choice is based on current official OpenAI guidance that new integrations
use Responses, while simple message arrays remain valid input. It creates a durable boundary for
the request and typed-output differences without introducing the SDK or agent/tool features.

## Offline and live verification

Offline tests use `respx` or provider stubs and make no network calls. Shared tests cover normalized
metadata, cost precedence/provenance, backward-compatible observation loading, error
classification, retries, and secret redaction. Focused provider tests cover credential resolution,
request shape, native model preservation, text and token extraction, actual model, optional
metadata/cost, missing fields, authentication, rate limiting, timeout/network failures,
server/provider failures, malformed responses, and retryability where applicable. A combined
offline benchmark test runs all three new providers through public `benchmark()` and persisted
artifacts while preserving existing provider suites.

Live pytest cases are independent and skip before setup if their key is absent:

- OpenRouter: `OPEN_ROUTER_API_KEY`, override `OPEN_ROUTER_TEST_MODEL`, default `openrouter/free`.
- Gemini: `GEMINI_API_KEY`, override `GEMINI_TEST_MODEL`, default `gemini-3.5-flash-lite`.
- OpenAI: `OPENAI_API_KEY`, override `OPENAI_TEST_MODEL`, default `gpt-6-luna`.

The defaults are point-in-time inexpensive, stable choices from current provider documentation;
the overrides are the durable interface when availability or account access differs. Each live
case uses a tiny deterministic text workload and small output limit through `benchmark()`, then
asserts a successful persisted observation/result without requiring optional metadata. Live tests
never print keys and normal tests never make live calls.

## Version, documentation, and release safety

Package/API/manifest/CI version reporting moves consistently to `0.2.0` while historical 0.1.0
release documents remain unchanged. README, changelog, contracts, examples, and 0.2.0 release
notes describe the release as multi-provider support and list all supported providers plus the
exact three new credential variables.

The distribution audit must recognize `OPEN_ROUTER_API_KEY`, `GEMINI_API_KEY`, and
`OPENAI_API_KEY` assignments as secrets, while allowing documented placeholders. Final review
checks that no credential value entered source, fixtures, logs, errors, artifacts, or packages and
that excluded providers/features did not enter implementation scope.

## Reference basis

These decisions use the provider documentation current when the 0.2.0 plan was revised:

- OpenRouter chat completions and metadata: <https://openrouter.ai/docs/api/api-reference/chat/create-a-chat-completion>
- OpenRouter free-model router: <https://openrouter.ai/openrouter/free>
- Gemini OpenAI compatibility and models: <https://ai.google.dev/gemini-api/docs/openai> and
  <https://ai.google.dev/gemini-api/docs/models>
- OpenAI Responses migration, request/response contract, and models:
  <https://developers.openai.com/api/docs/guides/migrate-to-responses>,
  <https://developers.openai.com/api/reference/cli/resources/responses/methods/create>, and
  <https://developers.openai.com/api/docs/models>
