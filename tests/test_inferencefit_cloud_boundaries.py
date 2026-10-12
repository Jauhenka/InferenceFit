"""Credential and candidate boundaries specific to the ``inferencefit-cloud`` provider."""

import secrets

import pytest
from pydantic import ValidationError

from inferencefit.contracts import CandidateSpec
from inferencefit.credentials import EnvironmentCredentialResolver
from inferencefit.errors import MissingCredentialError

CLOUD_PROVIDER = "inferencefit-cloud"
CLOUD_TOKEN_ENV = "INFERENCEFIT_CLOUD_TOKEN"


# --- Credential resolver ---------------------------------------------------


def test_cloud_fallback_reads_token_from_environment(monkeypatch):
    token = "cloud-" + secrets.token_hex(16)
    monkeypatch.setenv(CLOUD_TOKEN_ENV, token)
    resolver = EnvironmentCredentialResolver()
    assert resolver.resolve(None, CLOUD_PROVIDER) == token


def test_credential_ref_precedes_cloud_fallback(monkeypatch):
    monkeypatch.setenv(CLOUD_TOKEN_ENV, "fallback-token")
    monkeypatch.setenv("INFERENCEFIT_CREDENTIAL_NAMED", "reference-token")
    resolver = EnvironmentCredentialResolver()
    assert resolver.resolve("named", CLOUD_PROVIDER) == "reference-token"


def test_cloud_missing_token_raises_safe_error_naming_variable(monkeypatch):
    monkeypatch.delenv(CLOUD_TOKEN_ENV, raising=False)
    resolver = EnvironmentCredentialResolver()
    with pytest.raises(MissingCredentialError) as caught:
        resolver.resolve(None, CLOUD_PROVIDER)
    message = str(caught.value)
    assert CLOUD_TOKEN_ENV in message
    # The error must never echo a token value.
    assert "fallback-token" not in message


def test_cloud_token_is_not_externalized_in_error(monkeypatch):
    monkeypatch.delenv(CLOUD_TOKEN_ENV, raising=False)
    resolver = EnvironmentCredentialResolver()
    with pytest.raises(MissingCredentialError) as caught:
        resolver.resolve("named", CLOUD_PROVIDER)
    message = str(caught.value)
    assert CLOUD_TOKEN_ENV in message
    assert "INFERENCEFIT_CREDENTIAL_NAMED" in message


# --- Candidate validation --------------------------------------------------


@pytest.mark.parametrize(
    "base_url",
    [
        "https://cloud.example.test/v1",
        "http://localhost:8000/v1",
        "https://evil.example.test/v1?token=whatever",
        "HTTPS://Cloud.Example.Test/v1",
    ],
)
def test_cloud_rejects_any_base_url(base_url):
    with pytest.raises(ValidationError):
        CandidateSpec(id="c", provider=CLOUD_PROVIDER, model="opaque/model", base_url=base_url)


def test_cloud_rejects_pricing():
    with pytest.raises(ValidationError):
        CandidateSpec(
            id="c",
            provider=CLOUD_PROVIDER,
            model="opaque/model",
            pricing={"input_per_million": 1.0, "output_per_million": 2.0},
        )


def test_cloud_error_text_never_contains_token(monkeypatch):
    secret = "secret-" + secrets.token_hex(16)
    monkeypatch.setenv(CLOUD_TOKEN_ENV, secret)
    with pytest.raises(ValidationError) as caught:
        CandidateSpec(
            id="c",
            provider=CLOUD_PROVIDER,
            model="opaque/model",
            base_url=f"https://evil.example.test/v1?token={secret}",
        )
    message = str(caught.value)
    assert secret not in message


def test_cloud_accepts_plain_candidate():
    candidate = CandidateSpec(id="c", provider=CLOUD_PROVIDER, model="opaque/model")
    assert candidate.provider == CLOUD_PROVIDER
    assert candidate.base_url is None
    assert candidate.pricing is None


def test_cloud_credential_ref_is_allowed():
    candidate = CandidateSpec(
        id="c", provider=CLOUD_PROVIDER, model="opaque/model", credential_ref="named"
    )
    assert candidate.credential_ref == "named"


# --- Other providers are unaffected ----------------------------------------


def test_other_provider_keeps_base_url():
    candidate = CandidateSpec(
        id="c", provider="openai", model="m", base_url="https://api.openai.test/v1"
    )
    assert candidate.base_url == "https://api.openai.test/v1"


def test_other_provider_keeps_pricing():
    candidate = CandidateSpec(
        id="c",
        provider="openai",
        model="m",
        pricing={"input_per_million": 1.0, "output_per_million": 2.0},
    )
    assert candidate.pricing is not None


def test_cloud_identifier_case_variation_cannot_redirect_fallback_token():
    # The resolver lowercases provider names, so case variants must not fall
    # through to generic URL routing with the Cloud token.
    with pytest.raises(ValidationError):
        CandidateSpec(
            id="c", provider="InferenceFit-Cloud", model="m", base_url="https://example.test/v1"
        )
