from __future__ import annotations

import tarfile
import zipfile
from io import BytesIO
from pathlib import Path

import pytest
from scripts import audit_distribution as audit

WHEEL_NAME = "inferencefit-0.1.0-py3-none-any.whl"
SDIST_NAME = "inferencefit-0.1.0.tar.gz"


def write_wheel(path: Path, extra_members: dict[str, str] | None = None) -> None:
    members = {
        "inferencefit/__init__.py": '__version__ = "0.1.0"\n',
        "inferencefit-0.1.0.dist-info/METADATA": (
            "Metadata-Version: 2.1\nName: inferencefit\nVersion: 0.1.0\n"
        ),
        "inferencefit-0.1.0.dist-info/WHEEL": "Wheel-Version: 1.0\nTag: py3-none-any\n",
        "inferencefit-0.1.0.dist-info/licenses/LICENSE": "Apache License\n",
        "inferencefit-0.1.0.dist-info/entry_points.txt": (
            "[console_scripts]\ninferencefit = inferencefit.cli:app\n"
        ),
    }
    members.update(extra_members or {})
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in members.items():
            archive.writestr(name, content)


def write_sdist(path: Path) -> None:
    members = {
        "pyproject.toml": "[project]\nname = 'inferencefit'\n",
        "README.md": "# InferenceFit\n",
        "LICENSE": "Apache License\n",
        "CHANGELOG.md": "# Changelog\n",
        "src/inferencefit/__init__.py": '__version__ = "0.1.0"\n',
        "tests/test_smoke.py": "def test_smoke(): pass\n",
    }
    with tarfile.open(path, "w:gz") as archive:
        for name, content in members.items():
            encoded = content.encode()
            info = tarfile.TarInfo(f"inferencefit-0.1.0/{name}")
            info.size = len(encoded)
            archive.addfile(info, BytesIO(encoded))


def write_valid_distribution(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    dist.mkdir()
    write_wheel(dist / WHEEL_NAME)
    write_sdist(dist / SDIST_NAME)
    return dist


@pytest.mark.parametrize(
    "member",
    [
        "pkg/.env",
        "pkg/.inferencefit/runs/run/result.json",
        "pkg/.venv/pyvenv.cfg",
        "pkg/src/inferencefit/__pycache__/core.pyc",
        "pkg/AGENTS.md",
        "pkg/docs/superpowers/plans/internal.md",
    ],
)
def test_forbidden_archive_member_is_rejected(tmp_path: Path, member: str) -> None:
    dist = write_valid_distribution(tmp_path)
    write_wheel(dist / WHEEL_NAME, {member: "not for release\n"})

    with pytest.raises(audit.AuditError, match="forbidden"):
        audit.audit_distribution(dist, expected_version="0.1.0")


def test_path_traversal_member_is_rejected(tmp_path: Path) -> None:
    dist = write_valid_distribution(tmp_path)
    write_wheel(dist / WHEEL_NAME, {"../outside.txt": "escape\n"})

    with pytest.raises(audit.AuditError, match="traversal"):
        audit.audit_distribution(dist, expected_version="0.1.0")


def test_secret_like_content_is_rejected() -> None:
    findings = audit.scan_text("config.txt", "Bearer abcdefghijklmnopqrstuvwxyz123456")

    assert findings


def test_provider_key_assignment_is_rejected_from_archive(tmp_path: Path) -> None:
    dist = write_valid_distribution(tmp_path)
    write_wheel(dist / WHEEL_NAME, {"inferencefit/settings.py": "OPENAI_API_KEY=sk-secretvalue\n"})

    with pytest.raises(audit.AuditError, match="secret-like"):
        audit.audit_distribution(dist, expected_version="0.1.0")


def test_tag_version_must_match_distribution_version() -> None:
    with pytest.raises(audit.AuditError, match="expected version"):
        audit.assert_expected_version("0.1.0", "0.1.1")


def test_missing_required_wheel_license_is_rejected(tmp_path: Path) -> None:
    dist = write_valid_distribution(tmp_path)
    with zipfile.ZipFile(dist / WHEEL_NAME, "w") as archive:
        archive.writestr("inferencefit/__init__.py", "")
        archive.writestr(
            "inferencefit-0.1.0.dist-info/METADATA",
            "Metadata-Version: 2.1\nName: inferencefit\nVersion: 0.1.0\n",
        )
        archive.writestr("inferencefit-0.1.0.dist-info/WHEEL", "Wheel-Version: 1.0\n")
        archive.writestr("inferencefit-0.1.0.dist-info/entry_points.txt", "")

    with pytest.raises(audit.AuditError, match="licenses/LICENSE"):
        audit.audit_distribution(dist, expected_version="0.1.0")


def test_missing_required_sdist_content_is_rejected(tmp_path: Path) -> None:
    dist = write_valid_distribution(tmp_path)
    with tarfile.open(dist / SDIST_NAME, "w:gz") as archive:
        members = {
            "README.md": b"# InferenceFit\n",
            "LICENSE": b"Apache License\n",
            "CHANGELOG.md": b"# Changelog\n",
            "src/inferencefit/__init__.py": b'__version__ = "0.1.0"\n',
            "tests/test_smoke.py": b"def test_smoke(): pass\n",
        }
        for name, content in members.items():
            info = tarfile.TarInfo(f"inferencefit-0.1.0/{name}")
            info.size = len(content)
            archive.addfile(info, BytesIO(content))

    with pytest.raises(audit.AuditError, match="pyproject.toml"):
        audit.audit_distribution(dist, expected_version="0.1.0")


def test_clean_distribution_prints_deterministic_success_summary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dist = write_valid_distribution(tmp_path)

    assert audit.main([str(dist), "--expected-version", "0.1.0"]) == 0

    output = capsys.readouterr().out.splitlines()
    assert output == sorted(output)
    assert any(line.startswith(f"{SDIST_NAME}: ") and "bytes, 6 members" in line for line in output)
    assert any(line.startswith(f"{WHEEL_NAME}: ") and "bytes, 5 members" in line for line in output)
