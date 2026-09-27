"""Shared HTTP failure classifications with messages safe for persisted artifacts."""

import httpx

from .base import ProviderError


def provider_error_from_response(response: httpx.Response, *, provider: str) -> ProviderError:
    """Classify by status without copying remote content or request credentials.

    The provider argument identifies the calling adapter; it is deliberately not
    interpolated into the error because candidate labels are user-controlled.
    """
    status = response.status_code
    kind, retryable = {
        401: ("authentication", False),
        403: ("permission", False),
        408: ("timeout", True),
        429: ("rate_limit", True),
    }.get(status, ("server", True) if 500 <= status < 600 else ("http", False))
    return ProviderError(f"provider HTTP {status}", kind=kind, retryable=retryable)
