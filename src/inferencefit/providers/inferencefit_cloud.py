"""Client for the separately hosted InferenceFit Cloud inference gateway."""

from __future__ import annotations

import math
import os
import re
import secrets
import time
from urllib.parse import quote, urlsplit

import httpx

from inferencefit.contracts import CandidateSpec, TestCase

from .base import ProviderError, ProviderResponse
from .metadata import nonempty_string, nonnegative_token_count, safe_native_response

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
_ALLOWED_PARAMETERS = frozenset({"max_tokens", "temperature"})
_ERRORS = {
    "authentication_required": ("authentication", False),
    "insufficient_credits": ("insufficient_credits", False),
    "quota_exceeded": ("quota_exceeded", False),
    "unsupported_model": ("unsupported_model", False),
    "invalid_request": ("invalid_request", False),
    "idempotency_conflict": ("idempotency_conflict", False),
    "provider_failure": ("provider_failure", False),
    "rate_limited": ("rate_limit", True),
    "unknown_request_outcome": ("uncertain", False),
    "temporary_service_failure": ("server", True),
    "result_expired": ("result_expired", False),
}


def validate_cloud_origin(origin: str) -> str:
    """Require a deliberate trusted origin; never use a candidate URL."""

    invalid = ValueError("invalid InferenceFit Cloud origin")
    if not origin or any(char.isspace() or ord(char) < 32 for char in origin):
        raise invalid
    try:
        parsed = urlsplit(origin)
        _ = parsed.port
    except ValueError:
        raise invalid from None
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise invalid
    normalized = origin.rstrip("/")
    if parsed.hostname in _LOOPBACK_HOSTS:
        return normalized
    if (
        parsed.scheme != "https"
        or os.environ.get("INFERENCEFIT_CLOUD_TRUSTED_ORIGIN") != normalized
    ):
        raise ValueError("Cloud origin needs explicit trusted HTTPS configuration")
    return normalized


def cloud_origin_from_environment() -> str:
    """The benchmark specification has no influence over this setting."""

    origin = os.environ.get("INFERENCEFIT_CLOUD_API_URL")
    if not origin:
        raise ValueError("INFERENCEFIT_CLOUD_API_URL is required for Cloud access")
    return validate_cloud_origin(origin)


def _request_id(value: object) -> str | None:
    if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9._~-]{1,200}", value):
        return value
    return None


def _error(response: httpx.Response) -> ProviderError:
    if 300 <= response.status_code < 400:
        return ProviderError("InferenceFit Cloud origin redirected", kind="configuration")
    code = None
    request_id = None
    try:
        body = response.json()
        detail = body.get("error") if isinstance(body, dict) else None
        if isinstance(detail, dict):
            code = detail.get("code")
            request_id = _request_id(detail.get("request_id"))
    except ValueError:
        pass
    if code not in _ERRORS:
        code = "temporary_service_failure" if response.status_code >= 500 else "invalid_request"
    kind, retryable = _ERRORS[code]
    suffix = f" (Cloud request {request_id})" if request_id else ""
    return ProviderError(f"InferenceFit Cloud: {code}{suffix}", kind=kind, retryable=retryable)


class InferenceFitCloudProvider:
    """One billable Cloud invocation, with optional run-supplied identity."""

    def __init__(self, credential: str | None, origin: str | None = None):
        if not credential:
            raise ProviderError("INFERENCEFIT_CLOUD_TOKEN is required", kind="configuration")
        self.credential = credential
        self.origin = validate_cloud_origin(origin) if origin else cloud_origin_from_environment()

    def _headers(self, invocation_id: str | None = None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.credential}"}
        if invocation_id is not None:
            headers["Idempotency-Key"] = invocation_id
        return headers

    async def _get(self, path: str) -> dict:
        try:
            async with httpx.AsyncClient(
                timeout=10, follow_redirects=False, trust_env=False
            ) as client:
                response = await client.get(f"{self.origin}{path}", headers=self._headers())
        except httpx.HTTPError:
            raise ProviderError("InferenceFit Cloud unavailable", kind="network") from None
        if response.status_code != 200:
            raise _error(response)
        try:
            body = response.json()
        except ValueError:
            raise ProviderError("malformed Cloud response", kind="response") from None
        if not isinstance(body, dict):
            raise ProviderError("malformed Cloud response", kind="response")
        return safe_native_response(body, self.credential)

    async def account(self) -> dict:
        return await self._get("/v1/account")

    async def models(self) -> dict:
        return await self._get("/v1/models")

    async def request_status(self, request_id: str) -> dict:
        safe_id = _request_id(request_id)
        if safe_id is None:
            raise ProviderError("invalid Cloud request ID", kind="invalid_request")
        return await self._get(f"/v1/requests/{quote(safe_id, safe='')}")

    async def quote(self, candidate: CandidateSpec, case: TestCase) -> dict:
        payload = self._payload(candidate, case)
        try:
            async with httpx.AsyncClient(
                timeout=10, follow_redirects=False, trust_env=False
            ) as client:
                response = await client.post(
                    f"{self.origin}/v1/quotes", json=payload, headers=self._headers()
                )
        except httpx.HTTPError:
            raise ProviderError("InferenceFit Cloud unavailable", kind="network") from None
        if response.status_code != 200:
            raise _error(response)
        try:
            body = response.json()
        except ValueError:
            raise ProviderError("malformed Cloud quote", kind="response") from None
        if not isinstance(body, dict):
            raise ProviderError("malformed Cloud quote", kind="response")
        return safe_native_response(body, self.credential)

    @staticmethod
    def _payload(candidate: CandidateSpec, case: TestCase) -> dict:
        if candidate.provider != "inferencefit-cloud" or candidate.base_url or candidate.pricing:
            raise ProviderError("invalid Cloud candidate", kind="configuration")
        if set(candidate.parameters) - _ALLOWED_PARAMETERS:
            raise ProviderError("unsupported Cloud parameter", kind="configuration")
        max_tokens = candidate.parameters.get("max_tokens", 128)
        temperature = candidate.parameters.get("temperature")
        if type(max_tokens) is not int or max_tokens < 1:
            raise ProviderError("invalid Cloud max_tokens", kind="configuration")
        if temperature is not None and (
            type(temperature) not in (int, float)
            or not math.isfinite(temperature)
            or not 0 <= temperature <= 2
        ):
            raise ProviderError("invalid Cloud temperature", kind="configuration")
        payload = {
            "model": candidate.model,
            "messages": [
                message.model_dump(exclude_none=True) for message in case.request.messages
            ],
            "max_tokens": max_tokens,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        return payload

    async def complete(
        self, candidate: CandidateSpec, case: TestCase, repetition: int
    ) -> ProviderResponse:
        return await self.complete_with_invocation(
            candidate, case, repetition, f"ifc-{secrets.token_hex(24)}"
        )

    async def complete_with_invocation(
        self, candidate: CandidateSpec, case: TestCase, repetition: int, invocation_id: str
    ) -> ProviderResponse:
        if not re.fullmatch(r"[A-Za-z0-9._~-]{8,128}", invocation_id):
            raise ProviderError("invalid Cloud invocation ID", kind="configuration")
        payload = self._payload(candidate, case)
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(
                timeout=None, follow_redirects=False, trust_env=False
            ) as client:
                response = await client.post(
                    f"{self.origin}/v1/chat/completions",
                    json=payload,
                    headers=self._headers(invocation_id),
                )
        except httpx.TimeoutException:
            raise ProviderError("Cloud request timeout", kind="timeout", retryable=True) from None
        except httpx.HTTPError:
            raise ProviderError("Cloud transport failure", kind="network", retryable=True) from None
        latency_ms = (time.perf_counter() - started) * 1000
        if response.status_code != 200:
            raise _error(response)
        try:
            data = response.json()
            native = safe_native_response(data, self.credential)
            choice = native["choices"][0]
            content = choice["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError):
            raise ProviderError("malformed Cloud completion", kind="response") from None
        if not isinstance(content, str) or not isinstance(native, dict):
            raise ProviderError("malformed Cloud completion", kind="response")
        usage = native.get("usage")
        if not isinstance(usage, dict):
            usage = {}
        details = usage.get("completion_tokens_details")
        reasoning_tokens = (
            nonnegative_token_count(details.get("reasoning_tokens"))
            if isinstance(details, dict)
            else None
        )
        request_id = _request_id(native.get("request_id"))
        cost_usd = None
        if request_id:
            try:
                status = await self.request_status(request_id)
                charge = status.get("charged_micro_usd")
                if (
                    status.get("request_id") == request_id
                    and status.get("status") == "settled"
                    and type(charge) is int
                    and charge >= 0
                ):
                    cost_usd = charge / 1_000_000
            except ProviderError:
                pass  # Completed output remains useful; monetary cost is unknown.
        return ProviderResponse(
            raw_output=content,
            latency_ms=latency_ms,
            input_tokens=nonnegative_token_count(usage.get("prompt_tokens")),
            output_tokens=nonnegative_token_count(usage.get("completion_tokens")),
            total_tokens=nonnegative_token_count(usage.get("total_tokens")),
            cost_usd=cost_usd,
            provider="inferencefit-cloud",
            model=nonempty_string(native.get("model")) or candidate.model,
            raw_response=native,
            finish_reason=nonempty_string(choice.get("finish_reason")),
            provider_request_id=request_id,
            reasoning_tokens=reasoning_tokens,
            usage_details=usage or None,
        )
