"""Conservative metadata normalization for already-decoded provider JSON."""

from __future__ import annotations

import re
from typing import Any

import httpx

_SENSITIVE_KEYS = frozenset(
    {
        "authorization",
        "proxyauthorization",
        "xapikey",
        "apikey",
        "accesstoken",
        "refreshtoken",
        "clientsecret",
        "secretkey",
        "bearertoken",
        "token",
        "secret",
        "credential",
        "credentials",
        "password",
        "cookie",
        "setcookie",
    }
)
_BEARER_VALUE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}")
_KEY_VALUE = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}")
_ANTHROPIC_FINISH_REASONS = {
    "end_turn": "stop",
    "stop_sequence": "stop",
    "max_tokens": "length",
    "model_context_window_exceeded": "length",
    "tool_use": "tool_calls",
    "pause_turn": "pause",
    "refusal": "refusal",
}
_CHAT_FINISH_REASONS = {
    "stop": "stop",
    "length": "length",
    "tool_calls": "tool_calls",
    "function_call": "tool_calls",
    "content_filter": "content_filter",
}


def nonempty_string(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def nonnegative_token_count(value: Any) -> int | None:
    return value if type(value) is int and value >= 0 else None


def normalize_finish_reason(reason: str | None, *, anthropic: bool = False) -> str | None:
    if reason is None:
        return None
    mapping = _ANTHROPIC_FINISH_REASONS if anthropic else _CHAT_FINISH_REASONS
    return mapping.get(reason)


def safe_native_response(data: Any, credential: str | None) -> Any:
    """Keep native JSON but omit known credential fields and echoed resolved keys."""
    if isinstance(data, dict):
        safe = {}
        for key, value in data.items():
            normalized = re.sub(r"[^a-z0-9]", "", key.lower())
            safe_key = key.replace(credential, "[REDACTED]") if credential else key
            safe[safe_key] = (
                "[REDACTED]"
                if normalized in _SENSITIVE_KEYS
                else safe_native_response(value, credential)
            )
        return safe
    if isinstance(data, list):
        return [safe_native_response(value, credential) for value in data]
    if isinstance(data, str):
        value = data.replace(credential, "[REDACTED]") if credential else data
        value = _BEARER_VALUE.sub("[REDACTED]", value)
        return _KEY_VALUE.sub("[REDACTED]", value)
    return data


def provider_request_id(response: httpx.Response, credential: str | None) -> str | None:
    value = nonempty_string(response.headers.get("request-id")) or nonempty_string(
        response.headers.get("x-request-id")
    )
    if value is None:
        return None
    return safe_native_response(value, credential)
