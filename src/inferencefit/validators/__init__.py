"""Declarative validator execution."""

from __future__ import annotations

import importlib
import json
import re
from typing import Any

import jsonschema

from inferencefit.contracts import (
    CandidateResponse,
    TestCase,
    ValidationResult,
    ValidationSummary,
    ValidatorSpec,
)
from inferencefit.json_pointer import JsonPointerError, resolve_pointer


def _parsed(raw: str) -> Any:
    return json.loads(raw)


def _selected(spec: ValidatorSpec, case: TestCase, raw: str) -> tuple[Any, Any]:
    actual: Any = raw
    expected: Any = case.expected
    if spec.target is not None:
        actual = resolve_pointer(_parsed(raw), spec.target)
    if spec.reference is not None:
        expected = resolve_pointer(case.expected, spec.reference)
    return actual, expected


def _run(spec: ValidatorSpec, case: TestCase, raw: str) -> ValidationResult:
    try:
        actual, expected = _selected(spec, case, raw)
        cfg = spec.config
        if spec.type == "exact":
            passed = actual == expected
        elif spec.type == "regex":
            passed = re.search(str(cfg.get("pattern", "")), str(actual)) is not None
        elif spec.type == "enum":
            passed = actual in cfg.get("values", [])
        elif spec.type == "contains":
            passed = str(cfg.get("value", cfg.get("text", ""))) in str(actual)
        elif spec.type == "json_schema":
            document = _parsed(raw)
            if spec.target is not None:
                document = resolve_pointer(document, spec.target)
            jsonschema.validate(document, cfg.get("schema", cfg))
            passed = True
            actual = document
        elif spec.type == "numeric":
            tolerance = float(cfg.get("tolerance", cfg.get("absolute_tolerance", 0)))
            passed = abs(float(actual) - float(expected)) <= tolerance
        elif spec.type == "python":
            target = str(cfg.get("callable", ""))
            module_name, separator, attr = target.partition(":")
            if not separator:
                raise ValueError("python validator callable must be module:function")
            try:
                parsed_output = _parsed(raw)
            except json.JSONDecodeError:
                parsed_output = None
            response = CandidateResponse(raw_output=raw, parsed_output=parsed_output)
            result = getattr(importlib.import_module(module_name), attr)(case, response)
            if isinstance(result, ValidationResult):
                return result.model_copy(update={"runtime_capable": False})
            passed = bool(result)
        else:  # pragma: no cover - Literal protects this
            raise ValueError(f"unknown validator {spec.type}")
        return ValidationResult(
            validator_id=spec.id,
            passed=passed,
            observed=actual,
            expected=expected,
            message=None if passed else "validation failed",
            runtime_capable=spec.runtime_capable,
        )
    except (
        ValueError,
        TypeError,
        KeyError,
        JsonPointerError,
        json.JSONDecodeError,
        jsonschema.ValidationError,
    ) as exc:
        return ValidationResult(
            validator_id=spec.id,
            passed=False,
            message=str(exc),
            runtime_capable=spec.runtime_capable,
        )


def evaluate_validators(
    specs: list[ValidatorSpec], case: TestCase, raw_output: str
) -> ValidationSummary:
    results = [_run(spec, case, raw_output) for spec in specs]
    return ValidationSummary(passed=all(item.passed for item in results), results=results)


__all__ = ["evaluate_validators"]
