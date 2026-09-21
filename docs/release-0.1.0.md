# InferenceFit 0.1.0 release checklist

This is the living verification record for the first public InferenceFit release. It is
fail-closed: an unchecked required item keeps the release blocked. Record evidence from the
exact release candidate here; do not treat an older or provisional artifact as final evidence.

Status legend: `[x]` verified, `[ ]` pending or failed. Production publication and creation or
push of `v0.1.0` are outside this preparation task.

## Metadata and version

- [x] Distribution name is `inferencefit`.
- [x] `src/inferencefit/__init__.py` is the single maintained version source and reports
  `0.1.0`.
- [x] Hatch reads the dynamic version from that module; an installed package does not require
  Git metadata.
- [x] Package metadata declares `README.md`, Apache-2.0 and `LICENSE`, Python `>=3.11`, project
  URLs, classifiers, and keywords.
- [x] Runtime and development dependencies are separate; build, test, lint, and Twine tooling
  is development-only.
- [x] Metadata contract tests passed: `4 passed` on 2026-09-21. The full suite at that milestone
  was `76 passed, 2 warnings`.

Evidence: `pyproject.toml`, `src/inferencefit/__init__.py`,
`tests/test_release_metadata.py`, commit `137de06`.

## Tests and lint

- [x] Latest completed full-suite evidence: `134 passed, 2 warnings` on 2026-09-21 after the
  distribution-audit hardening.
- [x] Focused metadata and distribution-audit suite: `46 passed`.
- [x] Ruff check and format check passed for the Task 3 audit implementation and tests.
- [ ] Run the final full suite against the exact release candidate.
- [ ] Run repository-wide Ruff check and format check against the exact release candidate.
- [ ] Record the two known third-party FastAPI/Starlette deprecation warnings, or replace this
  note if final output differs.

Final commands and evidence:

```text
python -m pytest -q
Result: PENDING

python -m ruff check .
Result: PENDING

python -m ruff format --check .
Result: PENDING
```

## Clean build and artifacts

- [x] An isolated provisional build produced one wheel and one sdist with Hatchling 1.32.4.
- [x] After `CHANGELOG.md` was added, an isolated Task 4 build passed the distribution-content
  audit with 39 wheel members and 73 sdist members.
- [ ] Remove stale `dist/` and `build/` directories and rebuild from the exact release candidate.
- [ ] Run Twine checks on both final artifacts.
- [ ] Record exact final artifact names and byte sizes from the fresh build.

Observed isolated Task 4 artifacts on 2026-09-21 (audited successfully, but not final release
evidence because Tasks 5–8 may still change the candidate):

| Artifact | Observed size | Final size |
| --- | ---: | ---: |
| `inferencefit-0.1.0-py3-none-any.whl` | 38,274 bytes | PENDING |
| `inferencefit-0.1.0.tar.gz` | 66,046 bytes | PENDING |

Final commands and evidence:

```text
# PowerShell cleanup
Remove-Item -LiteralPath dist, build -Recurse -Force -ErrorAction SilentlyContinue

# POSIX cleanup
rm -rf dist build

python -m build
Result: PENDING

python -m twine check dist/*
Result: PENDING
```

## Installed wheel and sdist

- [x] A provisional `inferencefit-0.1.0-py3-none-any.whl` passed the clean-environment
  installed-distribution smoke on 2026-09-21. The verifier removed `PYTHONPATH`, ran outside
  the checkout, and rejected source-tree imports.
- [ ] Install and smoke-test the final wheel from the fresh build.
- [ ] Install and smoke-test the final sdist from the fresh build.

The verifier takes positional arguments: artifact, expected version, then source root.

```text
python scripts/verify_artifact_install.py dist/inferencefit-0.1.0-py3-none-any.whl 0.1.0 .
Final wheel result: PENDING

python scripts/verify_artifact_install.py dist/inferencefit-0.1.0.tar.gz 0.1.0 .
Final sdist result: PENDING
```

## CLI, Python API, and offline smoke

- [x] The public API exports `benchmark` and `__version__` from `inferencefit`.
- [x] The package defines the `inferencefit` console entry point.
- [x] The provisional installed-wheel smoke verified version `0.1.0`, `inferencefit --help`,
  `inferencefit validate`, and a deterministic two-case fixture benchmark with two provider
  successes, zero failures, one complete `result.json`, and `fixture` as the recommendation.
- [ ] Repeat all installed checks with the final wheel and final sdist.
- [ ] Run the public basic fixture from the release-candidate source tree and record the run.
- [ ] Run the public production-inspired fixture workload if it remains public in the candidate.

Source-tree commands and evidence:

```text
inferencefit validate examples/basic/eval.yaml
Result: PENDING

inferencefit benchmark examples/basic/eval.yaml
Result: PENDING

inferencefit validate examples/lead_semantic_units/eval.fixture.yaml
Result: PENDING

inferencefit benchmark examples/lead_semantic_units/eval.fixture.yaml
Result: PENDING
```

No paid Fireworks or DeepSeek run is required for this release pass; E0.5 already records the
successful live validation.

## Privacy and distribution-content audit

- [x] The archive auditor has mutation coverage for required contents, project/version identity,
  forbidden local state, traversal, duplicate/link/special members, resource limits, and
  secret-like content.
- [x] The final focused auditor test pass was included in the `46 passed` Task 3 run; two fresh
  DeepSeek reviews found no Critical or Important issue.
- [x] The committed E0.5 report states that the public lead example is synthetic and that exact
  credential-value and generic high-risk token scans found zero matches in the material checked
  during E0.5.
- [ ] Review the exact release-candidate tracked files for real identifiers, contact details,
  credentials, private URLs/IDs, and private production-derived inputs. Manually classify
  synthetic values such as `mira@example.test` and `+1-202-555-0147`; do not delete them solely
  because they look realistic.
- [x] The isolated Task 4 wheel and sdist passed the archive audit after `CHANGELOG.md` was added:
  39 wheel members and 73 sdist members, with no forbidden-state or secret-like finding.
- [ ] Repeat the successful audit against the final wheel and sdist and record exact final
  evidence.

```text
python scripts/audit_distribution.py dist --expected-version 0.1.0
Result: PENDING
Wheel member count: PENDING
Sdist member count: PENDING
Privacy-review notes: PENDING
```

## Python and CI coverage

- [x] Declared Python support and classifiers cover Python 3.11, 3.12, and 3.13.
- [x] The local development interpreter used for the prior task evidence currently reports
  Python 3.14.0 on Windows; this is supplemental evidence, not a declared 3.14 support claim.
- [ ] Verify Ubuntu on Python 3.11, 3.12, and 3.13 in GitHub Actions.
- [ ] Verify Windows on Python 3.13 in GitHub Actions.
- [ ] Verify the packaging job builds once, checks and audits both distributions, and smoke-tests
  final wheel and sdist without provider credentials or paid network inference.
- [ ] Record the CI workflow run URL and conclusion.

Evidence fields:

```text
Local interpreter: Python 3.14.0 / Windows NT 10.0.26200.0
CI workflow: PENDING (Task 5)
Ubuntu 3.11: PENDING
Ubuntu 3.12: PENDING
Ubuntu 3.13: PENDING
Windows 3.13: PENDING
Packaging job: PENDING
Run URL: PENDING
```

## PyPI and TestPyPI name checks

Check both indexes immediately before the readiness decision. A legitimate ownership conflict is
a release blocker; an HTTP 404 alone is evidence of no current project page, not a reservation.

- [ ] Check `inferencefit` on PyPI.
- [ ] Check `inferencefit` on TestPyPI.

```text
Checked at (UTC): PENDING
PyPI URL: https://pypi.org/project/inferencefit/
PyPI HTTP/result: PENDING
TestPyPI URL: https://test.pypi.org/project/inferencefit/
TestPyPI HTTP/result: PENDING
Conflict review: PENDING
```

## Trusted Publishing and publication rehearsal

- [ ] Add and verify `.github/workflows/testpypi.yml` with explicit dispatch, immutable build
  artifacts, environment `testpypi`, and OIDC only in the publish job.
- [ ] Add and verify `.github/workflows/release.yml` with a `v*` tag trigger, tag/version match,
  immutable build artifacts, environment `pypi`, and OIDC only in the publish job.
- [ ] Add exact owner setup instructions in `docs/releasing.md`.
- [ ] Confirm the GitHub environments `testpypi` and `pypi` exist; require human approval for
  production.
- [ ] Confirm the `inferencefit` Trusted Publisher relationships on TestPyPI and PyPI use the
  exact owner, repository, workflow filename, and environment.
- [ ] If already configured and intentionally approved, exercise TestPyPI; otherwise record it as
  not attempted and leave exact manual setup steps.
- [ ] Confirm no long-lived PyPI token is required or stored.

```text
TestPyPI workflow/configuration: PENDING (Task 6)
TestPyPI upload: PENDING / not attempted
Production workflow/configuration: PENDING (Task 6)
Production upload: NOT PERFORMED
```

## Blockers

Current release blockers:

- final clean build, Twine check, artifact audit, and exact size/member evidence are incomplete;
- final wheel and sdist clean-install smoke checks are incomplete;
- final full test, repository-wide lint/format, and public fixture runs are incomplete;
- cross-platform CI and packaging workflow evidence are incomplete;
- PyPI and TestPyPI name checks are incomplete;
- Trusted Publishing workflows, account-side configuration status, and owner instructions are
  incomplete;
- whole-branch review and final evidence refresh are incomplete.

Any failed correctness, install, content, privacy, name, CI, or workflow-security gate also blocks
the release until corrected. Account-side Trusted Publisher setup may remain a documented human
gate for a code-complete candidate, but publication must not proceed without it.

## Final decision

`BLOCKED_FOR_0.1.0`

Reason: release preparation is still in progress and the required Tasks 5–8 evidence above has
not been collected. Task 7 must replace this decision only after every required gate passes; do
not infer readiness from provisional artifacts.

Decision date (UTC): 2026-09-21

## Final human actions

Do not publish or tag yet. After Tasks 5–8 update this checklist to `READY_FOR_0.1.0`, the release
owner must:

1. review the final Git diff, checklist evidence, and passing GitHub Actions run;
2. configure and verify the `testpypi` and `pypi` GitHub environments and matching Trusted
   Publishers exactly as documented in `docs/releasing.md`;
3. intentionally run and verify the TestPyPI workflow if the publisher is configured;
4. merge or push the reviewed release commit through the repository's normal process;
5. only then create and push the annotated `v0.1.0` tag that triggers the production workflow;
6. manually approve the `pypi` environment after verifying that the workflow is publishing the
   already-verified immutable artifacts.

The exact push, workflow, and tag command sequence remains PENDING until Tasks 6–8 establish and
review the final workflow filenames and branch state. No production upload or tag push is
authorized by this checklist.
