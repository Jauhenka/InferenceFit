# Releasing InferenceFit

This guide is for the release owner of the `inferencefit` distribution. The source repository is
[`Jauhenka/InferenceFit`](https://github.com/Jauhenka/InferenceFit).

> [!IMPORTANT]
> The GitHub environments and PyPI/TestPyPI Trusted Publisher relationships are account-side
> settings. They are **pending until a release owner configures and verifies them**; their presence
> in this guide or in the workflow files is not evidence that setup is complete. Do not publish
> until every account-side check below is confirmed.

Publishing uses PyPI Trusted Publishing with short-lived OpenID Connect (OIDC) credentials. No
API token, `PYPI_API_TOKEN` secret, username/password, or `.pypirc` entry is required or expected.

## Trusted Publisher identities

Configure these two identities exactly; the project, repository, workflow filename, and
environment are matched claims rather than descriptive labels.

| Index | Project | GitHub owner | Repository | Workflow filename | GitHub environment |
| --- | --- | --- | --- | --- | --- |
| TestPyPI | `inferencefit` | `Jauhenka` | `InferenceFit` | `testpypi.yml` | `testpypi` |
| PyPI | `inferencefit` | `Jauhenka` | `InferenceFit` | `release.yml` | `pypi` |

1. In GitHub, open **Settings → Environments** for `Jauhenka/InferenceFit` and create the
   `testpypi` and `pypi` environments.
2. Protect `pypi` with required reviewers so every production deployment waits for an explicit
   human approval. Select the release-owner/reviewer team appropriate for the repository. Keep
   the production approval gate enabled for every release.
3. In [TestPyPI's pending-publisher settings](https://test.pypi.org/manage/account/publishing/),
   add the TestPyPI identity from the table.
4. In [PyPI's pending-publisher settings](https://pypi.org/manage/account/publishing/), add the
   production identity from the table.
5. Re-open both index settings and the two GitHub environments and compare every field with the
   table. Record that verification with the 0.2.4 release evidence.

For a first release, a pending publisher creates the project on its first successful upload. It
does **not** create the project or reserve the name when configured. If `inferencefit` already
exists on either index, stop and verify legitimate ownership before proceeding; do not assume the
pending publisher grants access.

## TestPyPI rehearsal

Do this once, after the reviewed release branch has been merged into `main` and before creating
the production tag. TestPyPI distribution files are immutable, so do not upload `0.2.4` from a
pre-merge commit and then attempt to replace it from a different merged commit.

1. Confirm `main` contains the reviewed `.github/workflows/testpypi.yml`. Record the exact current
   `main` commit SHA and require green CI for that same commit.
2. Confirm the TestPyPI pending publisher and the GitHub `testpypi` environment match the table
   above.
3. In GitHub, open **Actions → Publish to TestPyPI → Run workflow** and select `main` while its HEAD
   is the exact recorded commit. This workflow is manual; do not add a push or scheduled trigger.
4. Wait for its build, metadata check, distribution audit, wheel/sdist install checks, immutable
   artifact handoff, and publish job to succeed.
5. Verify the uploaded package in a clean virtual environment. TestPyPI is the package source;
   PyPI supplies dependencies that may not exist on TestPyPI:

   ```text
   python -m venv .venv-testpypi
   .venv-testpypi\Scripts\python -m pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ "inferencefit==0.2.4"
   .venv-testpypi\Scripts\python -c "import inferencefit; assert inferencefit.__version__ == '0.2.4'; print(inferencefit.__version__)"
   .venv-testpypi\Scripts\inferencefit --help
   ```

   On POSIX, use `.venv-testpypi/bin/python` and `.venv-testpypi/bin/inferencefit` instead. Verify
   that the reported version is exactly `0.2.4` and that the CLI help exits successfully.
6. Record the exact commit SHA, workflow run URL, conclusion, installed version, and CLI result in
   the 0.2.4 release evidence. A changed `main` SHA, missing publisher, failed upload, ambiguous
   package ownership, or failed install is a release blocker.

## Production release

Production publishing is deliberately tag-triggered and requires manual approval. Perform these
steps only after the release checklist says `READY_FOR_0.2.4`.

1. Push the reviewed release branch and merge it into `main` through the repository's normal
   reviewed process. Record the exact resulting `main` commit SHA; a squash or merge commit is a
   new candidate and must not inherit the branch commit's evidence.
2. Require green CI for that exact `main` commit, including Python 3.11–3.13, Windows,
   lint/format, build, Twine, archive audit, and installed wheel/sdist checks.
3. Run the TestPyPI workflow on that same exact `main` commit and require a successful, recorded
   rehearsal of `inferencefit==0.2.4`. If the merge changed the commit SHA, a branch rehearsal is
   not sufficient.
4. Confirm the PyPI Trusted Publisher and GitHub `pypi` environment match the table above, and
   confirm required reviewers/manual approval is active.
5. Update local `main` without rewriting history, set `verifiedReleaseSha` to the exact SHA that
   passed both CI and the TestPyPI rehearsal, refuse to continue if local `main` differs, then
   create and push exactly the annotated tag:

   ```text
   $verifiedReleaseSha = "<exact merged main SHA with green CI and successful TestPyPI>"
   git switch main
   git pull --ff-only
   if ((git rev-parse HEAD).Trim() -ne $verifiedReleaseSha) { throw "main is not the verified release commit" }
   $workingTreeChanges = git status --porcelain
   if ($workingTreeChanges) { throw "working tree is not clean" }
   git tag -a v0.2.4 -m "InferenceFit 0.2.4"
   git push origin v0.2.4
   ```

6. In the `release.yml` run, verify the tag-derived version is `0.2.4` and that every build and
   verification job is green. Before approving the `pypi` environment, confirm that the publish
   job downloads the already-verified `python-distributions` artifact and does not rebuild it.
7. A required reviewer then grants the production environment's manual approval. Verify the PyPI
   project page and a clean installation after publication.

Do not manually dispatch `release.yml`; production is triggered only by the pushed `v0.2.4` tag.
Do not push the tag until all preceding gates are complete.

## Failure and rollback boundary

Stop before approval if the tag, metadata version, artifact names, checks, package ownership, or
publisher identity differs from the expected release. Correct the release candidate first.

Once a distribution file is published to PyPI, it cannot be replaced with different content.
Deleting or yanking a release does not make the same filename/version safely reusable. If the
published `0.2.4` release is wrong, stop publication, document the incident, fix the repository,
increment to a new version, and release new artifacts through the complete process. Never attempt
to overwrite `0.2.4`.

References: [PyPA's Trusted Publishing workflow guide](https://packaging.python.org/en/latest/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/),
[PyPI pending publishers](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/),
and [installing from TestPyPI](https://packaging.python.org/en/latest/guides/using-testpypi/).
