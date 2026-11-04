"""Small objective live workload built on the ordinary benchmark pipeline."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from inferencefit.contracts import CandidateSpec, TestCase

# Historical configuration snapshots, not current prices or a provider price guarantee.
MODELS = [
    {
        "id": "fireworks",
        "provider": "fireworks",
        "model": "accounts/fireworks/models/nemotron-lightning-3p5-30b-a3b",
        "pricing": {"input_per_million": 0.05, "output_per_million": 0.20},
        "parameters": {"max_tokens": 64, "temperature": 0, "reasoning_effort": "none"},
    },
    {
        "id": "deepseek",
        "provider": "deepseek",
        "model": "deepseek-flash",
        "pricing": {"input_per_million": 0.30, "output_per_million": 1.20},
        "parameters": {"max_tokens": 64, "temperature": 0, "thinking": {"type": "disabled"}},
    },
]
KEYS = ("FIREWORKS_API_KEY", "DEEPSEEK_API_KEY")


def cases():
    values = [("red", "red"), ("blue", "blue"), ("green", "green"), ("yellow", "yellow")]
    return [
        TestCase.model_validate(
            {
                "id": str(i),
                "request": {
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                f'Extract the color from "The ball is {color}". '
                                'Return only JSON with key "color".'
                            ),
                        }
                    ]
                },
                "expected": {"color": answer},
            }
        )
        for i, (color, answer) in enumerate(values, 1)
    ]


def plan(budget):
    missing = [key for key in KEYS if not os.environ.get(key)]
    if missing:
        raise ValueError("Set both provider credentials: " + ", ".join(missing))
    candidates = [CandidateSpec.model_validate(x) for x in MODELS]
    workload = cases()
    total = sum(budget.estimate(c, case) for c in candidates for case in workload)
    return candidates, workload, total


def write_spec(directory: Path, candidates, workload):
    dataset = directory / "cases.jsonl"
    dataset.write_text(
        "".join(case.model_dump_json() + "\n" for case in workload), encoding="utf-8"
    )
    spec = {
        "schema_version": "0.1",
        "dataset": {"path": str(dataset)},
        "candidates": [c.model_dump(exclude_none=True) for c in candidates],
        "validators": [{"id": "exact", "type": "exact", "target": "", "reference": ""}],
        "optimization": {"objective": "balanced"},
        "execution": {
            "concurrency": 1,
            "repetitions": 1,
            "timeout_ms": 30000,
            "retry": {"max_attempts": 1},
        },
    }
    path = directory / "eval.yaml"
    path.write_text(yaml.safe_dump(spec), encoding="utf-8")
    return path
