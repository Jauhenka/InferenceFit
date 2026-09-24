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
- [x] The exact release candidate passed the final full suite: `169 passed, 2 warnings` on
  2026-09-24 under Python 3.14.0.
- [x] The complete suite also passed under supported Python 3.11.9 on Windows:
  `169 passed, 1 warning`.
- [x] Independent whole-branch review completed; all four Important findings were fixed with
  regression coverage and the complete local gate set was rerun afterward.
- [x] Repository-wide Ruff check and format check passed against the exact release candidate;
  Ruff reported `61 files already formatted`.
- [x] The final output retained the two known third-party FastAPI/Starlette deprecation warnings,
  recorded below.

Final commands and evidence:

```text
python -m pytest -q
Result: 169 passed, 2 warnings in 1.80s on Python 3.14.0
Python 3.11 result: 169 passed, 1 warning in 1.69s
Warnings: Starlette deprecates httpx with starlette.testclient; anyio.abc.BlockingPortal alias is
deprecated in favor of anyio.from_thread.BlockingPortal. Both originate in installed
FastAPI/Starlette dependencies during tests/test_engine.py::test_daemon_endpoints_use_shared_core.

python -m ruff check .
Result: All checks passed!

python -m ruff format --check .
Result: 61 files already formatted
```

## Clean build and artifacts

- [x] An isolated provisional build produced one wheel and one sdist with Hatchling 1.32.4.
- [x] After `CHANGELOG.md` was added, an isolated Task 4 build passed the distribution-content
  audit with 39 wheel members and 73 sdist members.
- [x] Removed only the validated repository-local `dist/` and `build/` directories and rebuilt
  from artifact-input commit `3e9e4c8a09e99704ca9261cfd14186f027fd6fe6`. The subsequently
  updated checklist is excluded from the sdist, eliminating self-referential artifact drift.
- [x] Twine checks passed on both final artifacts.
- [x] Recorded exact final artifact names, byte sizes, member counts, and SHA-256 digests.

Observed isolated Task 4 artifacts on 2026-09-21 (audited successfully, but not final release
evidence because Tasks 5–8 may still change the candidate):

| Artifact | Observed size | Final size |
| --- | ---: | ---: |
| `inferencefit-0.1.0-py3-none-any.whl` | 38,274 bytes | 38,274 bytes |
| `inferencefit-0.1.0.tar.gz` | 66,046 bytes | 67,146 bytes |

Final commands and evidence:

```text
# PowerShell cleanup
Remove-Item -LiteralPath dist, build -Recurse -Force -ErrorAction SilentlyContinue

# POSIX cleanup
rm -rf dist build

python -m build
Result: successfully built inferencefit-0.1.0.tar.gz and inferencefit-0.1.0-py3-none-any.whl
Build backend: Hatchling 1.32.4 in isolated environments

python -m twine check dist/*
Result: PASSED for both artifacts

Wheel: 38,274 bytes, 39 members
SHA-256: e90e3cbcc6205982731ebe64be7a479f54264aeb7ae6b2bd4db6a02c617cbaca
Sdist: 67,146 bytes, 73 members
SHA-256: 3141110641af86c9366a80bca7f3830352aae412d41febf5459faa8f6533584d
Planning/checklist members: 0 (`docs/implementation-plan.md` and
`docs/release-0.1.0.md` are excluded)
```

## Installed wheel and sdist

- [x] A provisional `inferencefit-0.1.0-py3-none-any.whl` passed the clean-environment
  installed-distribution smoke on 2026-09-21. The verifier removed `PYTHONPATH`, ran outside
  the checkout, and rejected source-tree imports.
- [x] The final wheel passed the clean-environment installed-distribution smoke.
- [x] The final sdist passed the clean-environment installed-distribution smoke.

The verifier takes positional arguments: artifact, expected version, then source root.

```text
python scripts/verify_artifact_install.py dist/inferencefit-0.1.0-py3-none-any.whl 0.1.0 .
Final wheel result: PASS (exit 0)

python scripts/verify_artifact_install.py dist/inferencefit-0.1.0.tar.gz 0.1.0 .
Final sdist result: PASS (exit 0)
```

## CLI, Python API, and offline smoke

- [x] The public API exports `benchmark` and `__version__` from `inferencefit`.
- [x] The package defines the `inferencefit` console entry point.
- [x] The provisional installed-wheel smoke verified version `0.1.0`, `inferencefit --help`,
  `inferencefit validate`, and a deterministic two-case fixture benchmark with two provider
  successes, zero failures, one complete `result.json`, and `fixture` as the recommendation.
- [x] Repeated all installed version/import/CLI/validation/fixture checks with the final wheel and
  final sdist; both passed in isolated virtual environments outside the checkout.
- [x] Ran the public basic fixture from the release-candidate source tree and recorded the run.
- [x] Ran the public production-inspired lead fixture workload and recorded the run.

Source-tree commands and evidence:

```text
inferencefit validate examples/basic/eval.yaml
Result: Valid EvaluationSpec 0.1, 2 candidates

inferencefit benchmark examples/basic/eval.yaml
Result: run 20260924T085543Z-ecfe52; 6 provider successes, 0 failures;
recommendation cascade:cheap->strong

inferencefit validate examples/lead_semantic_units/eval.fixture.yaml
Result: Valid EvaluationSpec 0.1, 2 candidates

inferencefit benchmark examples/lead_semantic_units/eval.fixture.yaml
Result: run 20260924T085544Z-0a1bfc; 48 provider successes, 0 failures;
recommendation cascade:cheap-fixture->strong-fixture
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
- [x] Reviewed the exact release-candidate tracked files for real identifiers, contact details,
  credentials, private URLs/IDs, and private production-derived inputs. Synthetic values such as
  `mira@example.test` and `+1-202-555-0147` were manually classified rather than rejected solely
  because they look realistic.
- [x] The isolated Task 4 wheel and sdist passed the archive audit after `CHANGELOG.md` was added:
  39 wheel members and 73 sdist members, with no forbidden-state or secret-like finding.
- [x] Repeated the successful audit against the final wheel and sdist and recorded exact final
  evidence.

```text
python scripts/audit_distribution.py dist --expected-version 0.1.0
Result: PASS
Wheel member count: 39
Sdist member count: 73
Privacy-review notes: PASS for all 80 tracked HEAD blobs and every archive member. No forbidden
tracked paths or artifact members were found. Two unique non-empty provider credential values
were compared byte-for-byte with tracked and packaged content; match count was zero and no value
was printed. All bearer/secret-prefix/key-assignment, email, phone, URL, model-ID, and run-ID hits
were manually classified as deliberate negative-test fixtures, explicitly synthetic public
examples, public documentation/provider endpoints, localhost defaults, or broad-regex false
positives. No private path, UUID, account/project/deployment identifier, or private raw input was
found.
```

## Python and CI coverage

- [x] Declared Python support and classifiers cover Python 3.11, 3.12, and 3.13.
- [x] The local development interpreter used for the prior task evidence currently reports
  Python 3.14.0 on Windows; this is supplemental evidence, not a declared 3.14 support claim.
- [x] The full suite passed locally on supported Python 3.11.9 on Windows.
- [ ] Verify Ubuntu on Python 3.11, 3.12, and 3.13 in GitHub Actions.
- [ ] Verify Windows on Python 3.13 in GitHub Actions.
- [x] Structural workflow tests verified that the packaging job builds once, checks and audits
  both distributions, and smoke-tests the final wheel and sdist without provider credentials or
  paid network inference.
- [ ] Record the CI workflow run URL and conclusion.

Evidence fields:

```text
Local interpreters: Python 3.14.0 and Python 3.11.9 / Windows NT 10.0.26200.0
CI workflow: implemented and structurally verified; exact candidate not pushed, so no run exists
Ubuntu 3.11: PENDING
Ubuntu 3.12: PENDING
Ubuntu 3.13: PENDING
Windows 3.13: PENDING
Packaging job: 23 workflow contract tests passed; runtime GitHub Actions evidence pending
Run URL: NONE -- public API returned zero workflow runs and local commit is absent from origin

The installed user-profile Python 3.11.9 runtime was accessed in the approved elevated
verification session through a disposable virtual environment; that environment reported
`inferencefit 0.1.0`, `pytest 9.1.1`, and the complete passing result above. Ordinary sandboxed
`py -0p` discovery lists Python 3.14 and 3.9 only. Python 3.12 and 3.13 were not available, so they
are not claimed as passed.
```

## PyPI and TestPyPI name checks

Check both indexes immediately before the readiness decision. A legitimate ownership conflict is
a release blocker; an HTTP 404 alone is evidence of no current project page, not a reservation.

- [x] Checked `inferencefit` on PyPI.
- [x] Checked `inferencefit` on TestPyPI.

```text
Checked at (UTC): 2026-09-24T22:21:18Z
PyPI URL: https://pypi.org/pypi/inferencefit/json
PyPI HTTP/result: 404 / available at check time
TestPyPI URL: https://test.pypi.org/pypi/inferencefit/json
TestPyPI HTTP/result: 404 / available at check time
Conflict review: no current project page on either official JSON endpoint; a 404 is not a name
reservation and must be rechecked immediately before publishing
```

## Trusted Publishing and publication rehearsal

- [x] Added and verified `.github/workflows/testpypi.yml` with explicit dispatch, immutable build
  artifacts, environment `testpypi`, and OIDC only in the publish job.
- [x] Added and verified `.github/workflows/release.yml` with a `v*` tag trigger, tag/version match,
  immutable build artifacts, environment `pypi`, and OIDC only in the publish job.
- [x] Added exact owner setup instructions in `docs/releasing.md`.
- [ ] Confirm the GitHub environments `testpypi` and `pypi` exist; require human approval for
  production.
- [ ] Confirm the `inferencefit` Trusted Publisher relationships on TestPyPI and PyPI use the
  exact owner, repository, workflow filename, and environment.
- [x] TestPyPI was not exercised because the GitHub environment and publisher are not configured;
  it is recorded as not attempted, with exact manual setup steps retained in `docs/releasing.md`.
- [x] Confirmed the workflows use OIDC only, require no long-lived PyPI token, and contain no
  publishing secret reference. The tracked/archive privacy scan found no credential value.

```text
TestPyPI workflow/configuration: repository workflow PASS; public GitHub API reports no
testpypi environment
TestPyPI upload: NOT ATTEMPTED -- publisher/environment not configured
Production workflow/configuration: repository workflow PASS; public GitHub API reports no
pypi environment
Production upload: NOT PERFORMED
```

## Blockers

The reviewed source, package metadata, workflows, artifacts, installed smoke checks, offline
examples, privacy scan, and package-name status have no remaining local blocker. The independent
whole-branch review's four Important findings were fixed with regression coverage, and every
local gate was rerun.

Current release blockers:

- the exact candidate commit is not on `origin`, the public repository has no workflow runs, and
  therefore Ubuntu Python 3.11/3.12/3.13, Windows Python 3.13, and the packaging job have no
  GitHub Actions runtime evidence;
- the public GitHub API reports no `testpypi` or `pypi` environments, so required production
  reviewers/manual approval are not configured;
- the TestPyPI and PyPI Trusted Publisher relationships cannot be confirmed and TestPyPI has not
  been rehearsed; publication must remain blocked until the owner completes and verifies the
  account-side setup.

Any failed correctness, install, content, privacy, name, CI, or workflow-security gate also blocks
the release until corrected. Account-side Trusted Publisher setup may remain a documented human
gate for a code-complete candidate, but publication must not proceed without it.

## Final decision

`BLOCKED_FOR_0.1.0`

Reason: all local code, documentation, build, install, offline-example, privacy, and package-name
gates pass, but the exact commit has no required cross-platform GitHub Actions run, the two GitHub
environments are absent, the Trusted Publisher relationships are unverified, and no TestPyPI
rehearsal exists. These are concrete fail-closed release blockers.

Decision date (UTC): 2026-09-24

## Final human actions

Do not publish or tag yet. After every recorded blocker is cleared and this checklist says
`READY_FOR_0.1.0`, the release owner must:

1. review the final Git diff and push `codex/release-0.1.0` for branch CI and normal review;
2. configure and verify the `testpypi` and `pypi` GitHub environments and matching Trusted
   Publishers exactly as documented in `docs/releasing.md`;
3. merge the reviewed branch into `main` through the repository's normal process and record the
   exact resulting commit SHA;
4. require green CI for that exact merged `main` commit;
5. intentionally run and verify the TestPyPI workflow on that same exact commit;
6. recheck both official package-name JSON endpoints, then create and push `v0.1.0` only if local
   `main` still equals the recorded CI-verified and TestPyPI-rehearsed SHA;
7. manually approve the `pypi` environment after verifying that the workflow is publishing the
   already-verified immutable artifacts.

Exact owner sequence after Task 8 review:

```text
git status
git push -u origin codex/release-0.1.0
# wait for branch CI and review to pass
# configure and verify the testpypi and pypi environments and Trusted Publishers per docs/releasing.md
# merge the reviewed branch into main through the repository's normal process
# record the exact resulting main commit SHA
# require green CI for that exact merged commit
# run Publish to TestPyPI on that exact commit and verify inferencefit==0.1.0
$verifiedReleaseSha = "<exact merged main SHA with green CI and successful TestPyPI>"
git switch main
git pull --ff-only
if ((git rev-parse HEAD).Trim() -ne $verifiedReleaseSha) { throw "main is not the verified release commit" }
$workingTreeChanges = git status --porcelain
if ($workingTreeChanges) { throw "working tree is not clean" }
# recheck https://pypi.org/pypi/inferencefit/json and https://test.pypi.org/pypi/inferencefit/json
git tag -a v0.1.0 -m "InferenceFit 0.1.0"
git push origin v0.1.0
```

None of those commands, uploads, merges, or approvals were performed by this preparation task.
