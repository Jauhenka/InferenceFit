"""OpenRouter chat completions with authoritative request metadata."""

from __future__ import annotations

import math

from inferencefit.contracts import CandidateSpec

from .openai_compatible import OpenAICompatibleProvider


class OpenRouterProvider(OpenAICompatibleProvider):
    def _base_url(self, candidate: CandidateSpec) -> str:
        return "https://openrouter.ai/api/v1"

    def _request_headers(self) -> dict[str, str]:
        return {**super()._request_headers(), "X-OpenRouter-Metadata": "enabled"}

    def _response_metadata(self, data: dict) -> dict:
        usage = data.get("usage")
        cost = usage.get("cost") if isinstance(usage, dict) else None
        cost_usd = None
        if type(cost) in (int, float) and cost >= 0:
            try:
                if math.isfinite(cost):
                    cost_usd = float(cost)
            except OverflowError:
                pass
        backend = data.get("provider")
        if not isinstance(backend, str) or not backend.strip():
            backend = None
        return {"cost_usd": cost_usd, "provider_backend": backend}
