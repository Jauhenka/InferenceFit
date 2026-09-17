from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable

from inferencefit.contracts import (
    CandidateSpec,
    EvaluationSpec,
    Observation,
    TestCase,
    TokenUsage,
)
from inferencefit.contracts.observations import ObservationError
from inferencefit.providers import ProviderAdapter, ProviderError
from inferencefit.storage import FilesystemArtifactStore
from inferencefit.validators import evaluate_validators

logger = logging.getLogger(__name__)


def _cost(
    candidate: CandidateSpec, input_tokens: int | None, output_tokens: int | None
) -> float | None:
    if candidate.pricing is None or input_tokens is None or output_tokens is None:
        return None
    if candidate.pricing.input_per_million is None or candidate.pricing.output_per_million is None:
        return None
    return (
        input_tokens * candidate.pricing.input_per_million
        + output_tokens * candidate.pricing.output_per_million
    ) / 1_000_000


async def _execute(
    candidate: CandidateSpec,
    case: TestCase,
    repetition: int,
    spec: EvaluationSpec,
    provider: ProviderAdapter,
) -> Observation:
    attempts = 0
    while True:
        attempts += 1
        try:
            response = await asyncio.wait_for(
                provider.complete(candidate, case, repetition),
                timeout=spec.execution.timeout_ms / 1000,
            )
            try:
                parsed = json.loads(response.raw_output)
            except json.JSONDecodeError:
                parsed = None
            validation = evaluate_validators(spec.validators, case, response.raw_output)
            return Observation(
                case_id=case.id,
                candidate_id=candidate.id,
                repetition=repetition,
                provider_status="success",
                raw_output=response.raw_output,
                parsed_output=parsed,
                usage=TokenUsage(
                    input_tokens=response.input_tokens, output_tokens=response.output_tokens
                ),
                latency_ms=response.latency_ms,
                cost_usd=_cost(candidate, response.input_tokens, response.output_tokens),
                provider_attempts=attempts,
                validation=validation,
            )
        except TimeoutError:
            error = ProviderError("request timeout", retryable=True, kind="timeout")
        except ProviderError as exc:
            error = exc
        if error.retryable and attempts < spec.execution.retry.max_attempts:
            delay = min(
                spec.execution.retry.initial_backoff_ms * (2 ** (attempts - 1)),
                spec.execution.retry.max_backoff_ms,
            )
            logger.warning(
                "retryable provider failure",
                extra={"candidate_id": candidate.id, "case_id": case.id, "attempt": attempts},
            )
            await asyncio.sleep(delay / 1000)
            continue
        return Observation(
            case_id=case.id,
            candidate_id=candidate.id,
            repetition=repetition,
            provider_status="error",
            provider_attempts=attempts,
            error=ObservationError(kind=error.kind, message=str(error), retryable=error.retryable),
        )


async def run_evaluations(
    spec: EvaluationSpec,
    cases: list[TestCase],
    provider_factory: Callable[[CandidateSpec], ProviderAdapter],
    store: FilesystemArtifactStore,
    run_id: str,
    existing: list[Observation] | None = None,
) -> list[Observation]:
    observations = list(existing or [])
    completed = {item.identity for item in observations}
    queue: asyncio.Queue[tuple[CandidateSpec, TestCase, int]] = asyncio.Queue()
    for candidate in spec.candidates:
        for case in cases:
            for repetition in range(spec.execution.repetitions):
                if (case.id, candidate.id, repetition) not in completed:
                    queue.put_nowait((candidate, case, repetition))

    async def worker() -> None:
        while True:
            try:
                item = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            try:
                candidate, case, repetition = item
                observation = await _execute(
                    candidate, case, repetition, spec, provider_factory(candidate)
                )
                store.append_observation(run_id, observation)
                observations.append(observation)
            finally:
                queue.task_done()

    count = min(spec.execution.concurrency, queue.qsize())
    async with asyncio.TaskGroup() as group:
        for _ in range(count):
            group.create_task(worker())
    return observations
