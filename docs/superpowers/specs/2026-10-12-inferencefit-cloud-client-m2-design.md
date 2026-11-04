# InferenceFit Cloud client integration (M2) design

## Intent and boundary

Add `inferencefit-cloud` as a normal provider in the public benchmark runner. Local fixture and BYOK candidates continue through the same runner, validators, observations, summaries, and optimization. The private Cloud repository remains unchanged. M2 uses a pre-provisioned account token; it does not implement signup, login, payments, or a second benchmark engine.

The public package is currently 0.2.5. Milestone 1 runs on `inferencefit==0.2.5`, but its PostgreSQL concurrency, crash, and deployment gates are still open. M2 can be verified offline against its actual FastAPI application with mocked upstream HTTP; no paid or production inference is authorized by this work.

## Actual Cloud HTTP contract

The Cloud API has `GET /health`, `/v1/models`, `/v1/account`, `/v1/account/usage`, `/v1/requests/{request_id}`, and `POST /v1/quotes`, `/v1/chat/completions`. `/v1` calls require `Authorization: Bearer <opaque token>`. Completion also requires an account-scoped `Idempotency-Key` of 8–128 ASCII characters. The accepted request is a strict text-only object: opaque catalog `model`, `messages` with system/user/assistant roles and a final user message, `max_tokens`, optional `temperature`. Unsupported fields are rejected. The response has an assistant choice, nullable normalized `finish_reason`, input/output/total usage, optional reasoning-token details, and a Cloud `request_id`.

The completion response **does not expose customer charge**. `GET /v1/requests/{id}` returns status and, once settled, `charged_micro_usd` as an integer. This is the only authoritative customer cost visible to the OSS client. It does not expose the actual native upstream served model; the response `model` is the catalog ID. A quote is a nonbillable reservation estimate and explicitly not a guaranteed maximum. Error bodies are `{error:{code,message,request_id}}`; the client uses only allowlisted codes and IDs, never arbitrary remote message text. A 202 `unknown_request_outcome` means the client must not create a new logical invocation.

## Credential and endpoint boundary

`EnvironmentCredentialResolver` gains the fallback `INFERENCEFIT_CLOUD_TOKEN`; existing opaque `credential_ref` resolution remains available. The token is never accepted as a literal candidate parameter or CLI option, included in artifacts, or logged. Missing and rejected credentials become distinct safe errors.

`CandidateSpec` rejects `base_url` and `pricing` for `inferencefit-cloud`. The provider registry selects a dedicated Cloud adapter **before** the generic `base_url` override path. The adapter has one trusted endpoint policy, configured outside evaluation YAML. Production uses the verified official HTTPS origin once confirmed; an explicitly configured loopback HTTP origin is permitted for local development and tests. No redirect is followed. The endpoint setting is never read from candidate parameters. A non-loopback custom origin must be a deliberate application-level trusted setting, documented as transferring token and workload data to that operator.

## Invocation identity and recovery

Every new benchmark run generates a random, nonsensitive invocation namespace and writes it to `manifest.json` before any provider dispatch. Resume reuses the namespace. A Cloud invocation key is a deterministic ASCII digest of `(namespace, candidate.id, case.id, repetition)`; it excludes retry attempt. Identical prompts in different runs have different namespaces, even when a caller reuses a run ID in another output directory. Existing 0.1 artifacts remain readable; no schema version change is needed.

The public `ProviderAdapter.complete(candidate, case, repetition)` contract remains intact. The runner may additionally call a provider-neutral, optional `complete_with_invocation(..., invocation_id)` capability. Existing adapters keep the current call path. The Cloud adapter uses the supplied identity as its `Idempotency-Key`; a direct standalone `complete()` gets a fresh identity. A retry by the runner uses the same key and payload. Cloud itself enforces duplicate suppression; no client-side assumption of exactly-once upstream execution is made.

On transport timeout or ambiguous failure, retrying the **same key** is safe from creating another Cloud request; a 202 or explicit uncertain result stops retries and reports its Cloud request ID where available. When a successful completion arrives, the adapter calls `/v1/requests/{id}` to obtain the settled customer charge. If the status lookup is unavailable or lacks a valid settled charge, the completion remains successful with unknown `cost_usd`, not zero and not an inferred token price. `provider_request_id` on the observation is the Cloud request ID. On resume, completed observations are skipped; an invocation without a stored observation reuses its original key and Cloud either replays the result or reports uncertain/expired status. Expired replay is surfaced without a second paid dispatch.

## Provider response and error mapping

The Cloud adapter returns text, usage, latency, catalog model ID, finish reason, Cloud request ID, and `cost_usd = charged_micro_usd / 1_000_000` only after settled status. `cost_source` remains `provider_reported` in the existing observation contract: here it means the remote Cloud service reported the **customer charge**. Cloud candidates may not supply local `pricing`, so the runner cannot apply its BYOK token-price fallback or a second markup. Optional response metadata may be absent without invalidating a completion.

Cloud error codes map to safe `ProviderError` kinds: missing token/configuration, authentication, insufficient credits, quota, unsupported model, invalid request, rate limit, provider failure, uncertain outcome, and temporary service failure. A provider may mark a transport failure retryable only when retry uses the same idempotency key. Insufficient credit and uncertain status are never blindly retried. No raw upstream error text or token enters the observation.

## CLI, example, and Agent Skill

`inferencefit cloud status`, `cloud models`, and `cloud balance` call the actual M1 API and print stable noninteractive output. They do not issue tokens or grant credit. A small quote wrapper may be shared by future agent tooling, but there is no full-run quote or exact spend-ceiling promise.

Documentation provides a development-only workflow with an operator-issued token and a mixed fixture/Cloud EvaluationSpec using synthetic cases and a deterministic validator. The Cloud model is an opaque catalog placeholder, not a recommended live model. The Agent Skill directs an agent to inspect Cloud configuration, model availability and balance, obtain approval before sending sensitive workload data or spending Cloud credit, bound requests and outputs, and keep tokens private. Offline and BYOK runs do not gain new prompts or steps.

## Verification and remaining dependencies

Tests cover credential and endpoint exfiltration, redirects, request/response and error parsing, stable idempotency across retry/repetition/run/resume, settled customer charge and unknown cost, CLI output, mixed benchmark artifacts, and a cross-repository FastAPI smoke with mocked upstream HTTP. Existing offline tests, style, build, distribution audit, clean wheel/sdist installs, and installed CLI smoke must pass. No live key is required. M1 PostgreSQL, crash, migration, and deployment gates remain separate production blockers. If the official production origin is not yet confirmed, production Cloud calls remain disabled by the endpoint policy until it is supplied.
