"""Local credential resolution."""

from __future__ import annotations

import os
import re

from inferencefit.errors import MissingCredentialError

_FALLBACKS = {"fireworks": "FIREWORKS_API_KEY", "openrouter": "OPENROUTER_API_KEY"}


class EnvironmentCredentialResolver:
    def variable_name(self, reference: str) -> str:
        normalized = re.sub(r"[^A-Za-z0-9]+", "_", reference).strip("_").upper()
        return f"INFERENCEFIT_CREDENTIAL_{normalized}"

    def resolve(self, reference: str | None, provider: str) -> str | None:
        names: list[str] = []
        if reference:
            names.append(self.variable_name(reference))
        fallback = _FALLBACKS.get(provider.lower())
        if fallback:
            names.append(fallback)
        for name in names:
            value = os.environ.get(name)
            if value:
                return value
        if not names:
            return None
        raise MissingCredentialError(
            f"credential reference {reference!r} is unavailable; checked {', '.join(names)}"
        )


__all__ = ["EnvironmentCredentialResolver"]
