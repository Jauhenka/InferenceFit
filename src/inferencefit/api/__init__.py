from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from inferencefit.core import benchmark, new_run_id
from inferencefit.dataset import load_jsonl_dataset
from inferencefit.spec import load_evaluation_spec

app = FastAPI(title="InferenceFit", version="0.1.0")


class RunRequest(BaseModel):
    spec_path: str
    output_root: str = ".inferencefit/runs"


@dataclass
class Job:
    state: str
    task: asyncio.Task | None = None
    result: object | None = None
    error: str | None = None
    output_root: Path | None = None
    planned_count: int = 0

    def completed_count(self) -> int:
        if self.output_root is None:
            return 0
        path = self.output_root / self.result_run_id / "observations.jsonl"
        if not path.exists():
            return 0
        return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())

    result_run_id: str = ""


jobs: dict[str, Job] = {}


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0"}


@app.post("/v1/runs", status_code=202)
async def create_run(request: RunRequest):
    provisional = new_run_id()
    job = Job(state="queued", output_root=Path(request.output_root), result_run_id=provisional)
    jobs[provisional] = job

    async def execute():
        job.state = "running"
        try:
            loaded = load_evaluation_spec(request.spec_path)
            dataset = load_jsonl_dataset(loaded.resolve_dataset_path())
            job.planned_count = (
                len(dataset) * len(loaded.spec.candidates) * loaded.spec.execution.repetitions
            )
            job.result = await benchmark(
                Path(request.spec_path),
                output_root=Path(request.output_root),
                run_id=provisional,
            )
            job.state = "completed"
        except asyncio.CancelledError:
            job.state = "cancelled"
        except Exception as exc:  # exposed without traceback or secrets
            job.error = type(exc).__name__
            job.state = "failed"

    job.task = asyncio.create_task(execute())
    return {"run_id": provisional, "state": job.state}


def _job(run_id: str) -> Job:
    if run_id not in jobs:
        raise HTTPException(404, "run not found")
    return jobs[run_id]


@app.get("/v1/runs/{run_id}")
async def run_status(run_id: str):
    job = _job(run_id)
    return {
        "run_id": run_id,
        "state": job.state,
        "error": job.error,
        "completed_count": job.completed_count(),
        "planned_count": job.planned_count,
    }


@app.get("/v1/runs/{run_id}/result")
async def run_result(run_id: str):
    job = _job(run_id)
    if job.result is None:
        raise HTTPException(409, "result is not ready")
    return job.result


@app.post("/v1/runs/{run_id}/cancel")
async def cancel_run(run_id: str):
    job = _job(run_id)
    if job.task and not job.task.done():
        job.task.cancel()
        job.state = "cancelled"
    return {"run_id": run_id, "state": job.state}
