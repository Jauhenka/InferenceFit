"""Offline checks of shared provider contracts and safe error normalization."""

import httpx
import pytest

from inferencefit.contracts import CandidateSpec, EvaluationSpec, Observation
from inferencefit.contracts import TestCase as Case
from inferencefit.execution.runner import _execute
from inferencefit.providers import ProviderError
from inferencefit.providers.openai_compatible import OpenAICompatibleProvider


def request_case():
    return Case.model_validate(
        {"id": "c", "request": {"messages": [{"role": "user", "content": "x"}]}}
    )


def test_legacy_observations_default_optional_metadata():
    observation = Observation.model_validate(
        {
            "schema_version": "0.1",
            "case_id": "c",
            "candidate_id": "x",
            "repetition": 0,
            "provider_status": "success",
            "usage": {"input_tokens": 2, "output_tokens": 3},
        }
    )
    assert observation.usage.total_tokens is None
    assert observation.provider is observation.model is observation.provider_backend is None
    assert observation.cost_source is None
    assert observation.schema_version == "0.1"


@pytest.mark.parametrize(
    "status,kind,retryable",
    [
        (400, "http", False),
        (401, "authentication", False),
        (403, "permission", False),
        (408, "timeout", True),
        (429, "rate_limit", True),
        (500, "server", True),
        (503, "server", True),
    ],
)
def test_shared_http_errors_are_classified_without_exposing_body(status, kind, retryable):
    from inferencefit.providers.http_errors import provider_error_from_response

    response = httpx.Response(
        status,
        json={"error": {"message": "secret-token response-body"}},
        request=httpx.Request(
            "POST", "https://example.test", headers={"Authorization": "secret-token"}
        ),
    )
    error = provider_error_from_response(response, provider="custom")
    assert isinstance(error, ProviderError)
    assert (error.kind, error.retryable) == (kind, retryable)
    assert "secret-token" not in str(error)
    assert "response-body" not in str(error)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,kind,retryable",
    [
        (401, "authentication", False),
        (403, "permission", False),
        (408, "timeout", True),
        (429, "rate_limit", True),
        (503, "server", True),
    ],
)
async def test_adapter_errors_persist_without_secrets(respx_mock, status, kind, retryable):
    respx_mock.post("https://example.test/v1/chat/completions").mock(
        return_value=httpx.Response(status, text="secret-token response-body")
    )
    spec = EvaluationSpec.model_validate(
        {
            "dataset": {"path": "unused"},
            "candidates": [
                {
                    "id": "x",
                    "provider": "custom",
                    "model": "m",
                    "base_url": "https://example.test/v1",
                }
            ],
            "execution": {"retry": {"max_attempts": 1}},
        }
    )
    observation = await _execute(
        spec.candidates[0], request_case(), 0, spec, OpenAICompatibleProvider("secret-token")
    )
    assert observation.error.kind == kind
    assert observation.error.retryable is retryable
    assert "secret-token" not in observation.model_dump_json()
    assert "response-body" not in observation.model_dump_json()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exception,kind", [(httpx.ReadTimeout, "timeout"), (httpx.ConnectError, "network")]
)
async def test_transport_errors_are_safe_and_retryable(respx_mock, exception, kind):
    respx_mock.post("https://example.test/v1/chat/completions").mock(
        side_effect=exception("secret-token")
    )
    candidate = CandidateSpec(
        id="x", provider="custom", model="m", base_url="https://example.test/v1"
    )
    with pytest.raises(ProviderError) as caught:
        await OpenAICompatibleProvider("secret-token").complete(candidate, request_case(), 0)
    assert caught.value.kind == kind
    assert caught.value.retryable is True
    assert "secret-token" not in str(caught.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "metadata",
    [
        {},
        {"usage": None, "model": None},
        {
            "usage": {"prompt_tokens": "bad", "completion_tokens": -1, "total_tokens": []},
            "model": {},
        },
    ],
)
async def test_optional_metadata_cannot_fail_successful_text(respx_mock, metadata):
    respx_mock.post("https://example.test/v1/chat/completions").mock(
        return_value=httpx.Response(
            200, json={"choices": [{"message": {"content": "answer"}}], **metadata}
        )
    )
    candidate = CandidateSpec(
        id="x", provider="custom", model="requested", base_url="https://example.test/v1"
    )
    response = await OpenAICompatibleProvider().complete(candidate, request_case(), 0)
    assert response.raw_output == "answer"
    assert response.model == "requested"
    assert response.input_tokens is response.output_tokens is response.total_tokens is None
