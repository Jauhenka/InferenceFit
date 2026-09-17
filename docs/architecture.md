# Architecture

InferenceFit is a modular Python monolith. The public Pydantic contracts are the center; dataset, credentials, validators, providers, execution, metrics, optimization, storage, and reporting point inward. `core.benchmark` composes them. Python exports, Typer, and FastAPI are thin entry points over that same orchestration path.

ProviderAdapter, validator dispatch, CredentialResolver, and FilesystemArtifactStore are boundaries because their implementations genuinely vary. Aggregation, constraints, Pareto dominance, ranking, and cascade selection are pure deterministic functions.

Execution uses a bounded `asyncio.Queue` worker pool rather than creating every request at once. Each terminal observation is appended and flushed immediately. Final JSON/YAML files use a temporary sibling plus atomic replacement. Resume validates spec and dataset hashes and skips existing terminal identities.

Local-first keeps sensitive datasets, outputs, and credentials under the user's control and makes fixture evaluation reproducible in CI. The filesystem artifacts are intentionally transparent rather than hidden in SQLite. Future remote workers or stores can implement the existing boundaries without moving optimization rules into infrastructure.

Provider failures are observations; validator failures are normal experiment outcomes; configuration errors fail before execution; internal errors remain errors. Retry is limited to timeouts, network faults, HTTP 429, and retryable 5xx responses.
