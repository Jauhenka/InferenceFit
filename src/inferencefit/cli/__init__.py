from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer

from inferencefit.agent_skill import canonical_skill_path
from inferencefit.core import benchmark as run_benchmark
from inferencefit.credentials import EnvironmentCredentialResolver
from inferencefit.errors import MissingCredentialError
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
