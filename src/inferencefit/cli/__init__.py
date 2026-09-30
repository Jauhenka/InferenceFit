from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer

from inferencefit.agent_skill import canonical_skill_path
from inferencefit.core import benchmark as run_benchmark
from inferencefit.presets import UnknownPresetError, list_presets
from inferencefit.presets.project import PresetDestinationError, initialize_project
from inferencefit.spec import load_evaluation_spec

app = typer.Typer(no_args_is_help=True, help="Workload-specific LLM benchmarking.")

skill_app = typer.Typer(no_args_is_help=True, help="Locate the packaged Agent Skill.")
app.add_typer(skill_app, name="skill")


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
