"""Cloud bearer credentials must remain bound to a trusted origin."""

from __future__ import annotations

from pathlib import Path

import pytest

from inferencefit.contracts import CandidateSpec
from inferencefit.credentials import EnvironmentCredentialResolver
from inferencefit.providers import InferenceFitCloudProvider, create_provider
from inferencefit.providers.inferencefit_cloud import validate_cloud_origin


def test_cloud_registry_selects_dedicated_adapter(monkeypatch):
    monkeypatch.setenv("INFERENCEFIT_CLOUD_TOKEN", "private-test-token")
    monkeypatch.setenv("INFERENCEFIT_CLOUD_API_URL", "http://127.0.0.1:8765")
    candidate = CandidateSpec(id="c", provider="inferencefit-cloud", model="opaque-id")
    adapter = create_provider(
        candidate, spec_dir=Path("."), resolver=EnvironmentCredentialResolver()
    )
    assert isinstance(adapter, InferenceFitCloudProvider)
    assert adapter.origin == "http://127.0.0.1:8765"


@pytest.mark.parametrize(
    "origin",
    [
        "http://evil.example:8000",
        "https://evil.example",
        "https://evil.example/path",
        "https://user:pass@evil.example",
        "https://evil.example?next=/steal",
        "https://evil.example#fragment",
    ],
)
def test_untrusted_origin_is_rejected_before_any_request(monkeypatch, origin):
    monkeypatch.delenv("INFERENCEFIT_CLOUD_TRUSTED_ORIGIN", raising=False)
    with pytest.raises(ValueError):
        validate_cloud_origin(origin)


def test_remote_https_requires_explicit_outside_spec_trust(monkeypatch):
    monkeypatch.setenv("INFERENCEFIT_CLOUD_TRUSTED_ORIGIN", "https://cloud.example")
    assert validate_cloud_origin("https://cloud.example") == "https://cloud.example"
    with pytest.raises(ValueError):
        validate_cloud_origin("http://cloud.example")
    with pytest.raises(ValueError):
        validate_cloud_origin("https://evil.example")


def test_model_construct_cannot_bypass_registry_cloud_url_protection(monkeypatch):
    monkeypatch.setenv("INFERENCEFIT_CLOUD_TOKEN", "private-test-token")
    candidate = CandidateSpec.model_construct(
        id="c",
        provider="inferencefit-cloud",
        model="opaque-id",
        base_url="https://evil.example",
    )
    with pytest.raises(ValueError, match="invalid InferenceFit Cloud candidate"):
        create_provider(candidate, spec_dir=Path("."), resolver=EnvironmentCredentialResolver())


def test_case_variant_cannot_enter_generic_routing(monkeypatch):
    monkeypatch.setenv("INFERENCEFIT_CLOUD_TOKEN", "private-test-token")
    candidate = CandidateSpec.model_construct(
        id="c",
        provider="InferenceFit-Cloud",
        model="opaque-id",
        base_url="https://evil.example",
    )
    with pytest.raises(ValueError, match="invalid InferenceFit Cloud candidate"):
        create_provider(candidate, spec_dir=Path("."), resolver=EnvironmentCredentialResolver())
