from typer.testing import CliRunner

from inferencefit.cli import app


def test_demo_help_and_missing_credentials(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("FIREWORKS_API_KEY", raising=False)
    runner = CliRunner()
    assert runner.invoke(app, ["demo", "--live", "--help"]).exit_code == 0
    result = runner.invoke(app, ["demo", "--live", "--yes", "--budget", "0.25"])
    assert result.exit_code != 0
    assert "DEEPSEEK_API_KEY" in result.output
    assert "FIREWORKS_API_KEY" in result.output


def test_noninteractive_and_offline(monkeypatch):
    runner = CliRunner()
    assert "no requests" in runner.invoke(app, ["demo"]).output
    result = runner.invoke(app, ["demo", "--live"])
    assert result.exit_code != 0
    assert "--yes" in result.output


def test_mocked_comparison(monkeypatch, tmp_path):
    import json

    import inferencefit.core as core
    from inferencefit.providers.base import ProviderResponse

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("FIREWORKS_API_KEY", "test-key")

    class FakeProvider:
        async def complete(self, candidate, case, repetition):
            return ProviderResponse(
                raw_output=json.dumps(case.expected),
                latency_ms=10,
                input_tokens=50,
                output_tokens=10,
            )

    monkeypatch.setattr(core, "create_provider", lambda *a, **kw: FakeProvider())
    result = CliRunner().invoke(app, ["demo", "--live", "--yes", "--budget", "0.25"])
    assert result.exit_code == 0, (result.output, result.exception)
    assert "Requests completed: 8" in result.output
    assert "4/4" in result.output
    assert "Recommendation:" in result.output
    assert "test-key" not in result.output


def test_budget_unknown_cost_and_exhaustion():
    from inferencefit.contracts import CandidateSpec, Observation
    from inferencefit.demo import MODELS, cases
    from inferencefit.execution.budget import BudgetController

    candidate = CandidateSpec.model_validate(MODELS[0])
    case = cases()[0]
    controller = BudgetController(0.25)
    amount = controller.estimate(candidate, case)
    controller.limit_usd = amount * 1.5
    assert controller.reserve(amount)
    controller.settle(
        Observation(
            case_id=case.id, candidate_id=candidate.id, repetition=0, provider_status="error"
        )
    )
    assert controller.uncertain == 1
    assert controller.uncertain_usd == amount
    assert not controller.reserve(amount)
    assert controller.stopped


def test_missing_price_fails_closed():
    import pytest

    from inferencefit.contracts import CandidateSpec
    from inferencefit.demo import cases
    from inferencefit.execution.budget import BudgetController

    candidate = CandidateSpec(
        id="x",
        provider="deepseek",
        model="x",
        parameters={"max_tokens": 64, "thinking": {"type": "disabled"}},
    )
    with pytest.raises(ValueError, match="pricing"):
        BudgetController(0.25).estimate(candidate, cases()[0])


def test_decline_and_insufficient_budget(monkeypatch):
    import inferencefit.cli as cli

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test")
    monkeypatch.setenv("FIREWORKS_API_KEY", "test")
    monkeypatch.setattr(cli, "_interactive", lambda: True)
    result = CliRunner().invoke(app, ["demo", "--live"], input="n\n")
    assert result.exit_code == 0
    assert "no requests" in result.output
    result = CliRunner().invoke(app, ["demo", "--live", "--yes", "--budget", "0.000000001"])
    assert result.exit_code == 2
    assert "no requests" in result.output


def test_partial_failure_and_missing_usage(monkeypatch, tmp_path):
    import json

    import inferencefit.core as core
    from inferencefit.providers.base import ProviderResponse

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test")
    monkeypatch.setenv("FIREWORKS_API_KEY", "test")
    count = 0

    class FakeProvider:
        async def complete(self, candidate, case, repetition):
            nonlocal count
            count += 1
            if count == 1:
                raise TimeoutError()
            return ProviderResponse(raw_output=json.dumps(case.expected), latency_ms=10)

    monkeypatch.setattr(core, "create_provider", lambda *a, **kw: FakeProvider())
    result = CliRunner().invoke(app, ["demo", "--live", "--yes", "--budget", "0.25"])
    assert result.exit_code != 0, (result.output, result.exception)
    assert "failures: 1; uncertain: 8" in result.output
    assert "no recommendation" in result.output
    assert "uncertain reservation: $0.000000" not in result.output


def test_budget_stops_between_requests(monkeypatch, tmp_path):
    import json

    import inferencefit.core as core
    from inferencefit.providers.base import ProviderResponse

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test")
    monkeypatch.setenv("FIREWORKS_API_KEY", "test")
    calls = []

    class FakeProvider:
        async def complete(self, candidate, case, repetition):
            calls.append(case.id)
            return ProviderResponse(raw_output=json.dumps(case.expected), latency_ms=10)

    monkeypatch.setattr(core, "create_provider", lambda *a, **kw: FakeProvider())
    result = CliRunner().invoke(app, ["demo", "--live", "--yes", "--budget", "0.0001"])
    assert result.exit_code != 0, (result.output, result.exception)
    assert 0 < len(calls) < 8
    assert "Budget exhaustion: True" in result.output
    assert "no recommendation" in result.output


def test_budget_stop_artifacts_record_planned_work_and_reason(monkeypatch, tmp_path):
    import json

    import inferencefit.core as core
    from inferencefit.providers.base import ProviderResponse

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test")
    monkeypatch.setenv("FIREWORKS_API_KEY", "test")

    class FakeProvider:
        async def complete(self, candidate, case, repetition):
            return ProviderResponse(raw_output=json.dumps(case.expected), latency_ms=10)

    monkeypatch.setattr(core, "create_provider", lambda *a, **kw: FakeProvider())
    result = CliRunner().invoke(app, ["demo", "--live", "--yes", "--budget", "0.0001"])
    assert result.exit_code != 0, (result.output, result.exception)
    run_dir = next((tmp_path / ".inferencefit" / "runs").iterdir())
    manifest = json.loads((run_dir / "manifest.json").read_text())
    bundle = json.loads((run_dir / "result.json").read_text())
    assert manifest["planned_observations"] == 8
    assert manifest["status"] == "incomplete"
    assert bundle["status"] == "failed"
    assert "budget" in bundle["recommendation_reason"].lower()
    assert bundle["recommendation"] is None


def test_demo_pricing_snapshot_is_not_padded_usage_cost():
    from inferencefit.contracts import CandidateSpec
    from inferencefit.demo import MODELS
    from inferencefit.execution.runner import _cost

    fireworks = CandidateSpec.model_validate(MODELS[0])
    deepseek = CandidateSpec.model_validate(MODELS[1])
    assert _cost(fireworks, 1_000_000, 1_000_000) == 0.25
    assert _cost(deepseek, 1_000_000, 1_000_000) == 1.5
