"""Offline CLI tests for the read-only ``inferencefit cloud`` commands.

Every HTTP interaction stays inside respx; no live Cloud endpoint or token is used.
"""

from __future__ import annotations

import httpx
import pytest
from typer.testing import CliRunner

from inferencefit.cli import app

ORIGIN = "http://127.0.0.1:8765"
TOKEN = "ifc_test_cloud_secret"

runner = CliRunner()

ACCOUNT = {
    "account_id": "acct_abc",
    "suspended": False,
    "balances": {
        "trial": {"available_micro_usd": 1000, "reserved_micro_usd": 0, "spent_micro_usd": 0},
        "paid": {"available_micro_usd": 500, "reserved_micro_usd": 25, "spent_micro_usd": 75},
    },
}

MODELS = {
    "data": [
        {
            "id": "model-a",
            "trial_enabled": True,
            "context_limit_tokens": 8192,
            "max_output_tokens": 1024,
            "pricing_version": "v1",
        },
        {
            "id": "model-b",
            "trial_enabled": False,
            "context_limit_tokens": 4096,
            "max_output_tokens": 512,
            "pricing_version": "v1",
        },
    ]
}


@pytest.fixture
def cloud_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INFERENCEFIT_CLOUD_TOKEN", TOKEN)
    monkeypatch.setenv("INFERENCEFIT_CLOUD_API_URL", ORIGIN)
    monkeypatch.delenv("INFERENCEFIT_CLOUD_TRUSTED_ORIGIN", raising=False)


def test_cloud_help_lists_commands() -> None:
    result = runner.invoke(app, ["cloud", "--help"])
    assert result.exit_code == 0
    for name in ("status", "models", "balance"):
        assert name in result.stdout


def test_status_reports_configured_and_authenticated(respx_mock, cloud_env: None) -> None:
    respx_mock.get(f"{ORIGIN}/v1/account").mock(return_value=httpx.Response(200, json=ACCOUNT))

    result = runner.invoke(app, ["cloud", "status"])

    assert result.exit_code == 0
    assert result.stderr == ""
    lines = result.stdout.splitlines()
    assert "Cloud configured: yes" in lines
    assert "Cloud authenticated: yes" in lines
    assert "Account: acct_abc" in lines
    assert "Suspended: no" in lines
    assert TOKEN not in result.output


def test_status_missing_token_is_safe_and_nonzero(
    respx_mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("INFERENCEFIT_CLOUD_TOKEN", raising=False)
    monkeypatch.setenv("INFERENCEFIT_CLOUD_API_URL", ORIGIN)

    result = runner.invoke(app, ["cloud", "status"])

    assert result.exit_code == 2
    assert result.stdout == ""
    assert "not configured" in result.stderr
    assert "INFERENCEFIT_CLOUD_TOKEN" in result.stderr
    assert "Traceback" not in result.stderr
    assert respx_mock.calls.call_count == 0


def test_status_missing_endpoint_is_safe_and_nonzero(
    respx_mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("INFERENCEFIT_CLOUD_TOKEN", TOKEN)
    monkeypatch.delenv("INFERENCEFIT_CLOUD_API_URL", raising=False)

    result = runner.invoke(app, ["cloud", "status"])

    assert result.exit_code == 2
    assert result.stdout == ""
    assert "not configured" in result.stderr
    assert TOKEN not in result.output
    assert "Traceback" not in result.stderr
    assert respx_mock.calls.call_count == 0


def test_status_invalid_token_is_distinct_and_nonzero(respx_mock, cloud_env: None) -> None:
    respx_mock.get(f"{ORIGIN}/v1/account").mock(
        return_value=httpx.Response(401, json={"error": {"code": "authentication_required"}})
    )

    result = runner.invoke(app, ["cloud", "status"])

    assert result.exit_code == 3
    assert result.stdout == ""
    assert "rejected" in result.stderr
    assert TOKEN not in result.output
    assert "Traceback" not in result.stderr


def test_status_unavailable_endpoint_is_distinct_and_nonzero(respx_mock, cloud_env: None) -> None:
    respx_mock.get(f"{ORIGIN}/v1/account").mock(
        side_effect=httpx.ConnectError("connection refused")
    )

    result = runner.invoke(app, ["cloud", "status"])

    assert result.exit_code == 4
    assert result.stdout == ""
    assert "unavailable" in result.stderr
    assert TOKEN not in result.output
    assert "Traceback" not in result.stderr


def test_models_prints_catalog_ids_only(respx_mock, cloud_env: None) -> None:
    respx_mock.get(f"{ORIGIN}/v1/models").mock(return_value=httpx.Response(200, json=MODELS))

    result = runner.invoke(app, ["cloud", "models"])

    assert result.exit_code == 0
    assert result.stderr == ""
    assert result.stdout == "model-a\nmodel-b\n"
    assert TOKEN not in result.output


def test_models_missing_token_is_safe_and_nonzero(
    respx_mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("INFERENCEFIT_CLOUD_TOKEN", raising=False)
    monkeypatch.setenv("INFERENCEFIT_CLOUD_API_URL", ORIGIN)

    result = runner.invoke(app, ["cloud", "models"])

    assert result.exit_code == 2
    assert result.stdout == ""
    assert "not configured" in result.stderr
    assert respx_mock.calls.call_count == 0


def test_balance_prints_exact_server_micro_usd(respx_mock, cloud_env: None) -> None:
    respx_mock.get(f"{ORIGIN}/v1/account").mock(return_value=httpx.Response(200, json=ACCOUNT))

    result = runner.invoke(app, ["cloud", "balance"])

    assert result.exit_code == 0
    assert result.stderr == ""
    assert result.stdout == (
        "Trial available (micro-USD): 1000\n"
        "Trial reserved (micro-USD): 0\n"
        "Trial spent (micro-USD): 0\n"
        "Paid available (micro-USD): 500\n"
        "Paid reserved (micro-USD): 25\n"
        "Paid spent (micro-USD): 75\n"
    )
    assert TOKEN not in result.output


def test_balance_invalid_token_is_distinct_and_nonzero(respx_mock, cloud_env: None) -> None:
    respx_mock.get(f"{ORIGIN}/v1/account").mock(
        return_value=httpx.Response(401, json={"error": {"code": "authentication_required"}})
    )

    result = runner.invoke(app, ["cloud", "balance"])

    assert result.exit_code == 3
    assert result.stdout == ""
    assert TOKEN not in result.output
    assert "Traceback" not in result.stderr
