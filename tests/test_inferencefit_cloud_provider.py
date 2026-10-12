"""Cloud adapter tests; every HTTP interaction stays inside respx."""

from __future__ import annotations

import httpx
import pytest

from inferencefit.contracts import CandidateSpec, TestCase
from inferencefit.providers import ProviderError
from inferencefit.providers.inferencefit_cloud import InferenceFitCloudProvider

ORIGIN = "http://127.0.0.1:8765"
TOKEN = "ifc_test_cloud_secret"


def candidate() -> CandidateSpec:
    return CandidateSpec(
        id="cloud",
        provider="inferencefit-cloud",
        model="opaque-catalog-id",
        parameters={"max_tokens": 12, "temperature": 0},
    )


def case() -> TestCase:
    return TestCase(id="case", request={"messages": [{"role": "user", "content": "hello"}]})


@pytest.mark.asyncio
async def test_completion_uses_cloud_contract_and_settled_customer_charge(respx_mock):
    completion = respx_mock.post(f"{ORIGIN}/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "chatcmpl-request-123",
                "object": "chat.completion",
                "model": "opaque-catalog-id",
                "request_id": "request-123",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "answer"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 4,
                    "completion_tokens": 3,
                    "total_tokens": 7,
                    "completion_tokens_details": {"reasoning_tokens": 1},
                },
            },
        )
    )
    status = respx_mock.get(f"{ORIGIN}/v1/requests/request-123").mock(
        return_value=httpx.Response(
            200, json={"request_id": "request-123", "status": "settled", "charged_micro_usd": 234}
        )
    )
    provider = InferenceFitCloudProvider(TOKEN, ORIGIN)
    response = await provider.complete_with_invocation(candidate(), case(), 0, "ifc-identity-123")
    assert response.raw_output == "answer"
    assert (response.input_tokens, response.output_tokens, response.total_tokens) == (4, 3, 7)
    assert response.model == "opaque-catalog-id"
    assert response.finish_reason == "stop"
    assert response.reasoning_tokens == 1
    assert response.provider_request_id == "request-123"
    assert response.cost_usd == pytest.approx(0.000234)
    assert completion.call_count == status.call_count == 1
    request = completion.calls[0].request
    assert request.headers["authorization"] == f"Bearer {TOKEN}"
    assert request.headers["idempotency-key"] == "ifc-identity-123"
    assert request.content == (
        b'{"model":"opaque-catalog-id","messages":[{"role":"user","content":"hello"}],'
        b'"max_tokens":12,"temperature":0}'
    )
    assert TOKEN not in repr(response.raw_response)


@pytest.mark.asyncio
async def test_missing_optional_metadata_and_unavailable_charge_remain_unknown(respx_mock):
    respx_mock.post(f"{ORIGIN}/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "request_id": "request-456",
                "choices": [{"message": {"content": "minimal"}}],
                "usage": {},
            },
        )
    )
    respx_mock.get(f"{ORIGIN}/v1/requests/request-456").mock(
        return_value=httpx.Response(503, json={"error": {"code": "temporary_service_failure"}})
    )
    response = await InferenceFitCloudProvider(TOKEN, ORIGIN).complete_with_invocation(
        candidate(), case(), 0, "ifc-identity-456"
    )
    assert response.raw_output == "minimal"
    assert response.cost_usd is None
    assert response.input_tokens is None
    assert response.finish_reason is None


@pytest.mark.asyncio
async def test_charge_requires_matching_request_identity(respx_mock):
    respx_mock.post(f"{ORIGIN}/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={"request_id": "request-ours", "choices": [{"message": {"content": "ok"}}]},
        )
    )
    respx_mock.get(f"{ORIGIN}/v1/requests/request-ours").mock(
        return_value=httpx.Response(
            200,
            json={"request_id": "request-other", "status": "settled", "charged_micro_usd": 900},
        )
    )
    response = await InferenceFitCloudProvider(TOKEN, ORIGIN).complete_with_invocation(
        candidate(), case(), 0, "ifc-identity-ours"
    )
    assert response.cost_usd is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("http_status", "code", "kind", "retryable"),
    [
        (401, "authentication_required", "authentication", False),
        (402, "insufficient_credits", "insufficient_credits", False),
        (429, "rate_limited", "rate_limit", True),
        (202, "unknown_request_outcome", "uncertain", False),
        (503, "temporary_service_failure", "server", True),
        (409, "idempotency_conflict", "idempotency_conflict", False),
    ],
)
async def test_cloud_errors_are_safe_and_classified(respx_mock, http_status, code, kind, retryable):
    respx_mock.post(f"{ORIGIN}/v1/chat/completions").mock(
        return_value=httpx.Response(
            http_status,
            json={"error": {"code": code, "message": TOKEN, "request_id": "request-err"}},
        )
    )
    with pytest.raises(ProviderError) as error:
        await InferenceFitCloudProvider(TOKEN, ORIGIN).complete_with_invocation(
            candidate(), case(), 0, "ifc-identity-error"
        )
    assert error.value.kind == kind
    assert error.value.retryable is retryable
    assert TOKEN not in str(error.value)
    assert "request-err" in str(error.value)


@pytest.mark.asyncio
async def test_uncertain_request_can_be_reconciled_by_request_id(respx_mock):
    respx_mock.post(f"{ORIGIN}/v1/chat/completions").mock(
        return_value=httpx.Response(
            202,
            json={"error": {"code": "unknown_request_outcome", "request_id": "request-pending"}},
        )
    )
    status_route = respx_mock.get(f"{ORIGIN}/v1/requests/request-pending").mock(
        return_value=httpx.Response(
            200,
            json={"request_id": "request-pending", "status": "uncertain", "charged_micro_usd": 0},
        )
    )
    provider = InferenceFitCloudProvider(TOKEN, ORIGIN)
    with pytest.raises(ProviderError, match="request-pending") as error:
        await provider.complete_with_invocation(candidate(), case(), 0, "ifc-pending-identity")
    assert error.value.kind == "uncertain"
    assert not error.value.retryable
    status = await provider.request_status("request-pending")
    assert status["status"] == "uncertain"
    assert status_route.call_count == 1


@pytest.mark.asyncio
async def test_transport_timeout_is_retryable_only_with_same_invocation_key(respx_mock):
    route = respx_mock.post(f"{ORIGIN}/v1/chat/completions").mock(
        side_effect=httpx.ReadTimeout("timed out")
    )
    provider = InferenceFitCloudProvider(TOKEN, ORIGIN)
    with pytest.raises(ProviderError) as error:
        await provider.complete_with_invocation(candidate(), case(), 0, "ifc-timeout-identity")
    assert error.value.kind == "timeout"
    assert error.value.retryable
    assert route.calls[0].request.headers["idempotency-key"] == "ifc-timeout-identity"


@pytest.mark.asyncio
async def test_redirect_does_not_send_token_to_other_origin(respx_mock):
    first = respx_mock.post(f"{ORIGIN}/v1/chat/completions").mock(
        return_value=httpx.Response(307, headers={"location": "https://evil.example/steal"})
    )
    evil = respx_mock.post("https://evil.example/steal").mock(
        return_value=httpx.Response(200, json={})
    )
    with pytest.raises(ProviderError) as error:
        await InferenceFitCloudProvider(TOKEN, ORIGIN).complete_with_invocation(
            candidate(), case(), 0, "ifc-identity-redirect"
        )
    assert error.value.kind == "configuration"
    assert first.call_count == 1
    assert evil.call_count == 0
