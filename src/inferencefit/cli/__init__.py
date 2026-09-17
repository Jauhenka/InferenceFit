from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from inferencefit.core import benchmark as run_benchmark
from inferencefit.spec import load_evaluation_spec

app = typer.Typer(no_args_is_help=True, help="Workload-specific LLM benchmarking.")


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
