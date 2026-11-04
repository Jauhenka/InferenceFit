"""Optional, conservative client-side reservations for sequential evaluations."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass

from inferencefit.contracts import CandidateSpec, Observation, TestCase


@dataclass
class BudgetController:
    limit_usd: float
    known_usd: float = 0.0
    uncertain_usd: float = 0.0
    completed: int = 0
    failed: int = 0
    uncertain: int = 0
    stopped: bool = False
    in_flight: float = 0.0

    def __post_init__(self):
        if not math.isfinite(self.limit_usd) or self.limit_usd <= 0:
            raise ValueError("Budget must be a positive finite USD amount")

    @staticmethod
    def input_token_estimate(case: TestCase) -> int:
        messages = [m.model_dump(exclude_none=True) for m in case.request.messages]
        return len(json.dumps(messages, ensure_ascii=False).encode("utf-8")) + 256

    def estimate(self, candidate: CandidateSpec, case: TestCase) -> float:
        if candidate.provider not in {"fireworks", "deepseek"} or candidate.base_url:
            raise ValueError("Budget estimation supports only the built-in demo provider endpoints")
        allowed = {"max_tokens", "temperature", "reasoning_effort", "thinking"}
        if set(candidate.parameters) - allowed:
            raise ValueError(f"Unsupported parameters for budget estimation: {candidate.id}")
        if candidate.provider == "deepseek" and candidate.parameters.get("thinking") != {
            "type": "disabled"
        }:
            raise ValueError("Budgeted DeepSeek requests must disable thinking")
        if (
            candidate.provider == "fireworks"
            and candidate.parameters.get("reasoning_effort") != "none"
        ):
            raise ValueError("Budgeted Fireworks requests must disable reasoning")
        pricing = candidate.pricing
        if (
            pricing is None
            or pricing.input_per_million is None
            or pricing.output_per_million is None
            or not all(
                math.isfinite(x) and x > 0
                for x in (pricing.input_per_million, pricing.output_per_million)
            )
        ):
            raise ValueError(f"Missing or invalid pricing for {candidate.id}; configure both rates")
        output = candidate.parameters.get("max_tokens")
        if type(output) is not int or not 0 < output <= 1024:
            raise ValueError(f"Set a bounded max_tokens (1–1024) for {candidate.id}")
        # Byte count plus framing allowance deliberately overestimates typical text tokenization;
        # provider-specific tokenization and charges are not guaranteed by this heuristic.
        input_tokens = self.input_token_estimate(case)
        # Pad the reservation, but leave configured rates unchanged for usage accounting.
        return (
            2
            * (input_tokens * pricing.input_per_million + output * pricing.output_per_million)
            / 1e6
        )

    def reserve(self, amount: float) -> bool:
        if self.known_usd + self.uncertain_usd + amount > self.limit_usd:
            self.stopped = True
            return False
        self.in_flight = amount
        return True

    def settle(self, observation: Observation) -> None:
        if observation.provider_status == "success":
            self.completed += 1
        else:
            self.failed += 1
        if (
            observation.cost_usd is None
            or not math.isfinite(observation.cost_usd)
            or observation.cost_usd < 0
        ):
            self.uncertain += 1
            self.uncertain_usd += self.in_flight
        else:
            self.known_usd += observation.cost_usd
        self.in_flight = 0.0

    def interrupt(self) -> None:
        if self.in_flight:
            self.uncertain += 1
            self.uncertain_usd += self.in_flight
            self.in_flight = 0.0
