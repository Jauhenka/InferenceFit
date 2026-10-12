"""Opt-in dependency smoke against the sibling M1 FastAPI application."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import httpx
import pytest


@pytest.mark.asyncio
async def test_actual_cloud_gateway_completion_and_charge(monkeypatch):
    cloud_root = Path(__file__).resolve().parents[2] / "inferencefit-cloud"
    if not (cloud_root / "src/inferencefit_cloud/api.py").is_file():
        pytest.skip("sibling inferencefit-cloud checkout is unavailable")
    missing = [
        name
        for name in ("sqlalchemy", "cryptography", "alembic", "psycopg")
        if not importlib.util.find_spec(name)
    ]
    if missing:
        pytest.skip(f"cross-repository Cloud dependencies unavailable: {', '.join(missing)}")
    monkeypatch.syspath_prepend(str(cloud_root / "src"))

    from cryptography.fernet import Fernet
    from inferencefit_cloud import models  # noqa: F401
    from inferencefit_cloud.admin import bootstrap
    from inferencefit_cloud.api import create_app
    from inferencefit_cloud.catalog import CatalogEntry, sync_entry
    from inferencefit_cloud.config import Settings
    from inferencefit_cloud.db import Base, get_session
    from inferencefit_cloud.models import GatewayRequest, PlatformBudget
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from inferencefit.contracts import CandidateSpec, TestCase
    from inferencefit.providers.inferencefit_cloud import InferenceFitCloudProvider

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    settings = Settings(
        database_url="sqlite+pysqlite:///:memory:",
        result_encryption_key=Fernet.generate_key().decode(),
        open_router_api_key="dummy",
        inferencefit_cloud_enabled=True,
    )
    with factory() as session:
        session.add(PlatformBudget(id=1, reserved_provider_micro=0, spent_provider_micro=0))
        _, token = bootstrap(session, "m2-contract", settings.trial_grant_micro)
        sync_entry(
            session,
            CatalogEntry(
                cloud_model_id="alpha-test",
                provider_model_id="vendor/model/with/slashes",
                enabled=True,
                trial_enabled=True,
                metering_verified=True,
                input_price_micro_per_million=100_000,
                output_price_micro_per_million=200_000,
                max_input_bytes=4_096,
                max_output_tokens=256,
                pricing_version=1,
                pricing_effective_at="2026-10-12T00:00:00Z",
            ),
            "test",
        )
        session.commit()
    app = create_app(settings)

    def sessions():
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = sessions
    original_client = httpx.AsyncClient
    asgi = httpx.ASGITransport(app=app)
    upstream_calls = []

    class RoutedTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            if request.url.host == "127.0.0.1":
                return await asgi.handle_async_request(request)
            if request.url.host == "openrouter.ai":
                upstream_calls.append(request)
                return httpx.Response(
                    200,
                    json={
                        "model": "vendor/model/with/slashes",
                        "choices": [
                            {
                                "message": {"content": "actual-gateway-answer"},
                                "finish_reason": "stop",
                            }
                        ],
                        "usage": {
                            "prompt_tokens": 5,
                            "completion_tokens": 3,
                            "total_tokens": 8,
                            "cost": 0.0001,
                        },
                    },
                    request=request,
                )
            raise AssertionError(f"unexpected HTTP destination: {request.url.host}")

    transport = RoutedTransport()

    def client_with_transport(*args, **kwargs):
        return original_client(*args, transport=transport, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client_with_transport)
    try:
        provider = InferenceFitCloudProvider(token, "http://127.0.0.1:8765")
        candidate = CandidateSpec(
            id="cloud",
            provider="inferencefit-cloud",
            model="alpha-test",
            parameters={"max_tokens": 10},
        )
        case = TestCase(id="case", request={"messages": [{"role": "user", "content": "hello"}]})
        response = await provider.complete_with_invocation(
            candidate, case, 0, "ifc-cross-repository-contract-1"
        )
        assert response.raw_output == "actual-gateway-answer"
        assert response.cost_usd == pytest.approx(0.0002)
        assert response.finish_reason == "stop"
        assert response.provider_request_id
        assert len(upstream_calls) == 1
        assert upstream_calls[0].headers["authorization"] == (
            f"Bearer {settings.open_router_api_key}"
        )
        with factory() as session:
            record = session.scalar(select(GatewayRequest))
            assert record.state == "settled"
            assert record.charged_micro == 200
        assert token not in repr(response.raw_response)
    finally:
        engine.dispose()
