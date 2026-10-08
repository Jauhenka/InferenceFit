# Validator selection

Choose the strongest deterministic evidence the workload genuinely supports.

## Available shapes

- `json_schema` checks parseability, required fields, types, and allowed properties. It can be a
  runtime routing gate, but valid structure does not prove a correct answer.
- `exact` compares a parsed target with an expected reference. It is evaluation-only and is useful
  for labels, canonical fields, and deterministic transformations.
- `numeric` compares numbers with configured tolerance. Use it for measured values where exact
  representation is too strict.
- `regex`, `enum`, and `contains` check constrained surface properties and may be routing gates.
- `python` calls local custom validation logic.

Exact and contains validators are not semantic evaluation. They can reject equivalent wording or
accept text that contains a token without satisfying the task. For semantic tasks, use reviewed
representative cases and an explicit task-specific rubric; version 0.2.4 has no built-in semantic
judge.

Local Python validators are trusted code. Review their module and dependencies before running them,
keep them deterministic, and never generate or execute validator code from untrusted model output.
Prefer existing unit tests, schemas, and programmatic invariants over invented references.

Use a runtime-capable validator as a routing gate only when failure is observable from the response
alone. Hidden expected answers belong in evaluation-only validators.
