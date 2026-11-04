from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated

import typer

from inferencefit import demo as demo_module
from inferencefit.agent_skill import canonical_skill_path
from inferencefit.core import benchmark as run_benchmark
from inferencefit.credentials import EnvironmentCredentialResolver
from inferencefit.errors import MissingCredentialError
from inferencefit.execution.budget import BudgetController
from inferencefit.presets import UnknownPresetError, list_presets
from inferencefit.presets.project import PresetDestinationError, initialize_project
from inferencefit.providers import ProviderError
from inferencefit.providers.inferencefit_cloud import InferenceFitCloudProvider
from inferencefit.spec import load_evaluation_spec

app = typer.Typer(no_args_is_help=True, help="Workload-specific LLM benchmarking.")

skill_app = typer.Typer(no_args_is_help=True, help="Locate the packaged Agent Skill.")
app.add_typer(skill_app, name="skill")
cloud_app = typer.Typer(no_args_is_help=True, help="Inspect an authorized Cloud account.")
app.add_typer(cloud_app, name="cloud")


def _cloud_provider() -> InferenceFitCloudProvider:
    try:
        token = EnvironmentCredentialResolver().resolve(None, "inferencefit-cloud")
        return InferenceFitCloudProvider(token)
    except (MissingCredentialError, ValueError) as exc:
        typer.echo(f"Cloud not configured: {exc}", err=True)
        raise typer.Exit(code=2) from None


def _cloud_read(method: str) -> dict:
    provider = _cloud_provider()
    try:
        return asyncio.run(getattr(provider, method)())
    except ProviderError as exc:
        if exc.kind == "authentication":
            typer.echo("Cloud credential rejected", err=True)
            raise typer.Exit(code=3) from None
        if exc.kind in ("network", "server"):
            typer.echo("Cloud endpoint unavailable", err=True)
            raise typer.Exit(code=4) from None
        typer.echo(f"Cloud request failed: {exc.kind}", err=True)
        raise typer.Exit(code=1) from None


@cloud_app.command("status")
def cloud_status_command() -> None:
    """Check Cloud configuration and account authentication."""

    account = _cloud_read("account")
    account_id = account.get("account_id")
    suspended = account.get("suspended")
    if not isinstance(account_id, str) or type(suspended) is not bool:
        typer.echo("Malformed Cloud account response", err=True)
        raise typer.Exit(code=1)
    typer.echo("Cloud configured: yes")
    typer.echo("Cloud authenticated: yes")
    typer.echo(f"Account: {account_id}")
    typer.echo(f"Suspended: {'yes' if suspended else 'no'}")


@cloud_app.command("models")
def cloud_models_command() -> None:
    """List server-owned hosted model IDs."""

    models = _cloud_read("models").get("data")
    if not isinstance(models, list) or any(
        not isinstance(item, dict) or not isinstance(item.get("id"), str) for item in models
    ):
        typer.echo("Malformed Cloud models response", err=True)
        raise typer.Exit(code=1)
    for item in models:
        typer.echo(item["id"])


@cloud_app.command("balance")
def cloud_balance_command() -> None:
    """Show exact server-reported trial and paid micro-USD balances."""

    balances = _cloud_read("account").get("balances")
    if not isinstance(balances, dict):
        typer.echo("Malformed Cloud balance response", err=True)
        raise typer.Exit(code=1)
    lines = []
    for bucket in ("trial", "paid"):
        wallet = balances.get(bucket)
        if not isinstance(wallet, dict):
            typer.echo("Malformed Cloud balance response", err=True)
            raise typer.Exit(code=1)
        for field in ("available", "reserved", "spent"):
            value = wallet.get(f"{field}_micro_usd")
            if type(value) is not int or value < 0:
                typer.echo("Malformed Cloud balance response", err=True)
                raise typer.Exit(code=1)
            lines.append(f"{bucket.title()} {field} (micro-USD): {value}")
    for line in lines:
        typer.echo(line)


@skill_app.command("path")
def skill_path_command() -> None:
    """Print the absolute path to the canonical Agent Skill directory."""

    typer.echo(str(canonical_skill_path()))


@app.command("presets")
def presets_command() -> None:
    """List the built-in workload presets."""

    for preset in list_presets():
        typer.echo(f"{preset.identifier}: {preset.description}")


@app.command("init")
def init_command(
    destination: Annotated[Path, typer.Argument(metavar="DESTINATION")],
    preset: Annotated[
        str,
        typer.Option("--preset", help="Built-in workload preset identifier."),
    ],
) -> None:
    """Create a starter benchmark project from a built-in preset."""

    target = destination.expanduser().absolute()
    try:
        created = initialize_project(preset, target)
    except UnknownPresetError:
        typer.echo(
            f"Unknown preset '{preset}'. Run 'inferencefit presets' to list available presets.",
            err=True,
        )
        raise typer.Exit(code=2) from None
    except PresetDestinationError as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(code=2) from None
    except Exception as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(code=1) from None

    typer.echo(f"Initialized {preset} preset at {target}")
    typer.echo("Created:")
    for path in created:
        typer.echo(f"  {path.relative_to(target).as_posix()}")
    typer.echo(
        "Replace the sample cases with representative production examples before using the "
        "benchmark for model-selection decisions."
    )
    typer.echo("Replace the fixture candidate with the models you actually want to evaluate.")
    typer.echo("Next:")
    typer.echo(f"  inferencefit benchmark {target / 'eval.yaml'}")


def _interactive() -> bool:
    return sys.stdin.isatty()


@app.command("demo")
def demo_command(
    live: bool = typer.Option(False, "--live", help="Run the live provider comparison."),
    yes: bool = typer.Option(False, "--yes", help="Explicitly consent to provider requests."),
    budget: float | None = typer.Option(None, "--budget", help="USD budget (default: 0.25)."),
) -> None:
    """Run a small, explicitly authorized live comparison."""
    if not live:
        typer.echo("Offline: no requests made. Use --live to plan a live comparison.")
        return
    if not _interactive() and (not yes or budget is None):
        typer.echo("Non-interactive use requires --yes and an explicit --budget.", err=True)
        raise typer.Exit(2)
    try:
        controller = BudgetController(0.25 if budget is None else budget)
        candidates, workload, estimate = demo_module.plan(controller)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from None
    typer.echo("InferenceFit Live Demo")
    for candidate in candidates:
        pricing = candidate.pricing
        typer.echo(
            f"  {candidate.provider}: {candidate.model} "
            f"(snapshot USD/M tokens: input {pricing.input_per_million}, "
            f"output {pricing.output_per_million})"
        )
    typer.echo(f"Test cases: {len(workload)}; planned requests: {len(workload) * len(candidates)}")
    typer.echo(f"Estimated reservation: ${estimate:.6f}; budget: ${controller.limit_usd:.2f}")
    input_total = sum(controller.input_token_estimate(case) for case in workload) * len(candidates)
    typer.echo(
        f"Estimated input tokens: {input_total}; output token limit: "
        f"{64 * len(workload) * len(candidates)} total."
    )
    typer.echo("Input estimate uses UTF-8 bytes plus framing; provider counts can differ.")
    typer.echo("Price snapshots checked 2026-11-04; DeepSeek uses peak cache-miss rates.")
    typer.echo("Estimates use padded snapshots and token heuristics, not a billing guarantee.")
    typer.echo("Test prompts will be sent to the selected providers.")
    if not yes and not typer.confirm("Proceed?", default=False):
        typer.echo("Declined; no requests made.")
        raise typer.Exit(0)
    if controller.estimate(candidates[0], workload[0]) > controller.limit_usd:
        typer.echo("Budget insufficient for the first request; no requests made.", err=True)
        raise typer.Exit(2)
    try:
        with TemporaryDirectory(prefix="inferencefit-demo-") as directory:
            spec = demo_module.write_spec(Path(directory), candidates, workload)
            result = asyncio.run(run_benchmark(spec, budget=controller))
    except (KeyboardInterrupt, Exception) as exc:
        controller.interrupt()
        typer.echo(f"Demo interrupted or failed ({type(exc).__name__}).", err=True)
        typer.echo(
            f"Reported/estimated cost: ${controller.known_usd:.6f}; "
            f"uncertain reservation: ${controller.uncertain_usd:.6f}",
            err=True,
        )
        raise typer.Exit(1) from None
    typer.echo("Model | attempted | quality | reliability | p50 ms | estimated cost")
    for summary in result.candidate_summaries:
        latency = "unknown" if summary.p50_latency_ms is None else f"{summary.p50_latency_ms:.0f}"
        cost = "unknown" if summary.total_cost_usd is None else f"${summary.total_cost_usd:.6f}"
        typer.echo(
            f"{summary.id} | {summary.planned_count}/{len(workload)} | "
            f"{summary.validation_pass_count}/{len(workload)} | "
            f"{summary.provider_success_count}/{summary.planned_count} | {latency} | {cost}"
        )
    typer.echo(
        f"Requests completed: {controller.completed}; failures: {controller.failed}; "
        f"uncertain: {controller.uncertain}"
    )
    typer.echo(
        f"Reported/estimated cost: ${controller.known_usd:.6f}; "
        f"uncertain reservation: ${controller.uncertain_usd:.6f}"
    )
    if controller.stopped or controller.failed or controller.uncertain:
        typer.echo(
            "Incomplete or uncertain results: no recommendation. Budget exhaustion: "
            + str(controller.stopped)
        )
    else:
        typer.echo(
            f"Recommendation: {result.recommendation} "
            "(balanced quality, cost, latency and reliability)."
        )
    typer.echo(f"Artifacts: .inferencefit/runs/{result.run_id}")
    typer.echo("Small smoke test only; use more representative cases before selecting a model.")
    typer.echo("Next: inferencefit init --preset structured-extraction ./eval")


@app.command("validate")
def validate_command(spec: Path) -> None:
    loaded = load_evaluation_spec(spec)
    typer.echo(
        f"Valid EvaluationSpec 0.1: {len(loaded.spec.candidates)} candidate(s), "
        f"dataset={loaded.resolve_dataset_path()}"
    )


@app.command("benchmark")
def benchmark_command(spec: Path, resume: str | None = None) -> None:
    result = asyncio.run(run_benchmark(spec, resume=resume))
    successes = sum(x.provider_success_count for x in result.candidate_summaries)
    failures = sum(x.provider_error_count for x in result.candidate_summaries)
    typer.echo(f"Run: {result.run_id}")
    typer.echo(f"Candidates: {len(result.candidate_summaries)}")
    typer.echo(f"Provider successes/failures: {successes}/{failures}")
    typer.echo(f"Recommendation: {result.recommendation}")
    typer.echo(f"Artifacts: .inferencefit/runs/{result.run_id}")


@app.command("serve")
def serve(host: str = "127.0.0.1", port: int = 8787) -> None:
    import uvicorn

    uvicorn.run("inferencefit.api:app", host=host, port=port)
