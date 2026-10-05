# Decentralized Inference Providers 0.2.3 Design

## Decision and scope

Add `chutes`, `morpheus`, and `nosana` as named profiles over the existing non-streaming `OpenAICompatibleProvider`. Keep `schema_version: "0.1"`, native model IDs, the shared benchmark path, configured pricing, and existing explicit `base_url` override behavior. No provider subclasses, common contract fields, public model-discovery API, wallet integration, automatic pricing, or streaming.

The 0.2.2 `custom` route already provides OpenAI-compatible chat completions. The branded names add a maintained endpoint, conventional credential fallback, provider identity in observations, concrete setup guidance, and provider-specific opt-in smoke checks.

| Provider | What `custom` already does | Branded value | Cost / risk | Decision |
| --- | --- | --- | --- | --- |
| Chutes | Sends Bearer chat requests to an explicit URL | Fixed gateway and key name; identifiable results; current-catalog live check | Six profile lines shared across three services; model and pricing metadata change | Include |
| Morpheus | Same transport | Fixed hosted gateway, key name, and careful trust-boundary guidance | Gateway routing and model availability change; no machine-readable prices in active model list | Include, with no decentralization or attestation guarantee |
| Nosana | Same transport | Fixed gateway and key name; live check against currently served models | Availability changes; a catalog lookup is needed in opt-in live tests | Include |

The marginal runtime value is modest, particularly for Morpheus. The integrations are still worthwhile as low-cost named configuration and documented test paths. Complexity added solely to distinguish them from `custom` would make the release worse.

## Verified API facts and limits

Research checked current first-party documentation on 2026-10-05. Provider catalogs, model prices, and availability may change; these are observations, not frozen contracts.

| Provider | Hosted chat base and authentication | Catalog and pricing | Response and trust boundary |
| --- | --- | --- | --- |
| Chutes | `https://llm.chutes.ai/v1`; Bearer API key. [Guide](https://chutes.ai/docs/guides/starter-guide) | Public `GET /v1/models` currently exposes native IDs, modality, `price.input.usd` / `price.output.usd`, `pricing.prompt` / `pricing.completion`, and `confidential_compute`. Price numbers are per million tokens in the current catalog; no model ID is stable enough for a product default. [Catalog](https://llm.chutes.ai/v1/models) | Chat completions expose standard usage; no verified authoritative per-request monetary cost. TEE metadata is model metadata, not proof that an entire benchmark path is confidential. No common TEE field. |
| Morpheus | `https://api.mor.org/api/v1`; hosted gateway with Bearer API key, documented as `MORPHEUS_API_KEY`. [Quickstart](https://apidocs.mor.org/quickstart) | Authenticated `GET /models` lists active models; `/models/allmodels` includes inactive ones. Active list has no machine-readable pricing. A separate [pricing page](https://apidocs.mor.org/documentation/models/pricing) is human-readable and will not be scraped. [Models](https://apidocs.mor.org/api-reference/models/list) | Chat completions have standard token usage, no verified request cost. The managed gateway is distinct from direct node and on-chain paths; its own hop is not cryptographically attested. Provider-side TEE claims do not cover every external hop. [API docs](https://apidocs.mor.org/api-reference/chat/completions) |
| Nosana | `https://inference.nosana.com/v1`; Bearer API key. [LLM API](https://learn.nosana.com/api/llm.html) | Authenticated `GET /v1/models` represents models currently served. It provides ID, context length, max output, availability, and prompt/completion prices in USD **per token**. This differs from Chutes units. | Chat usage gives token counts, not verified monetary request cost. The separate usage-history API can report cost, but completion-to-history correlation adds billing and timing complexity; omit. A model-not-found error can reflect no GPU currently serving it; retain generic error/retry policy. |

No provider-specific metadata or retry normalization is justified. A `base_url` override for any of these branded names follows existing 0.2.2 dispatch behavior. Provider identifiers remain lowercase; existing candidate contracts do not canonicalize case. Unknown names with explicit URL remain deprecated compatibility, while new generic configurations use `provider: custom`.

## Model selection, cost, and safety

Normal benchmarking requires the user's explicit native model ID and never fetches a catalog. No static default model, runtime catalog dependency, or automatic cheapest-model selection is added. Opt-in live tests may make one read-only `GET /models`: Chutes' public catalog exposes modality and price fields sufficient to select a low-price text model without a key, while `CHUTES_TEST_MODEL` overrides it. Morpheus requires `MORPHEUS_TEST_MODEL` because its active-model list lacks machine-readable prices. Nosana requires `NOSANA_TEST_MODEL`; its authenticated catalog is used to confirm that ID is currently served. Although Nosana exposes availability and price, it has no reliable chat/reasoning capability field: an actual catalog contained an embedding model, and a low-price reasoning model returned no answer with a 32-token cap. A missing suitable model skips with a safe reason. The actual inference always goes through public `benchmark()` with one case, one repetition, bounded output, and `execution.retry.max_attempts: 1`.

Catalog prices are not equivalent to authoritative request charges and have different units across services. In 0.2.3, only user-supplied `pricing` populates calculated cost; otherwise monetary cost stays unknown. Resolved secrets are never written to specs, observations, results, logs, errors, examples, or artifacts. Opaque `credential_ref` follows the existing persistence contract. The shared adapter continues rejecting reserved `model`, `messages`, and `stream` request parameters before HTTP.

## Files and release behavior

Add preset URL entries in `src/inferencefit/providers/openai_compatible.py` and fallbacks in `src/inferencefit/credentials/__init__.py`; the registry derives known names from presets and routes all three to the shared adapter. Add parameterized profile and public benchmark tests, opt-in live checks, one minimal example per service, README/contracts/Skill guidance, 0.2.3 release metadata and versioned CI checks. Installed wheel/sdist smoke remains offline. Keep historical release documents intact.

Out of scope: other providers, direct network protocols, wallets, blockchain transactions, staking, token accounting, deployment APIs, billing, SDKs, UI, plugin systems, Cloud, model ranking, price scraping, and streaming.
