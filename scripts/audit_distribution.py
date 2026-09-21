"""Inspect release archives without extracting their untrusted members."""

from __future__ import annotations

import argparse
import re
import sys
import tarfile
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


class AuditError(ValueError):
    """A distribution archive does not meet the release policy."""


@dataclass(frozen=True)
class ArtifactSummary:
    name: str
    size: int
    member_count: int


FORBIDDEN_COMPONENTS = frozenset({".env", ".inferencefit", ".venv", "__pycache__", "AGENTS.md"})
FORBIDDEN_SUFFIXES = (".pyc",)
TEXT_SECRET_PATTERNS = (
    re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]{20,}"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}"),
    re.compile(
        r"(?im)\b(?:OPENAI|ANTHROPIC|FIREWORKS|AZURE|GOOGLE|AWS)_"
        r"(?:API_)?(?:KEY|TOKEN|SECRET)\s*=\s*['\"]?\S+"
    ),
)

WHEEL_REQUIRED_SUFFIXES = (
    ".dist-info/METADATA",
    ".dist-info/WHEEL",
    ".dist-info/entry_points.txt",
    ".dist-info/licenses/LICENSE",
)
SDIST_REQUIRED_MEMBERS = frozenset(
    {
        "pyproject.toml",
        "README.md",
        "LICENSE",
        "CHANGELOG.md",
        "src/inferencefit/__init__.py",
    }
)


def scan_text(member: str, text: str) -> list[str]:
    """Return descriptions of credential-like values found in archive text."""
    return [
        f"{member}: secret-like content" for pattern in TEXT_SECRET_PATTERNS if pattern.search(text)
    ]


def assert_expected_version(expected: str, actual: str) -> None:
    if expected != actual:
        raise AuditError(f"expected version {expected}, found {actual}")


def _normalized_member_name(name: str) -> str:
    normalized = name.replace("\\", "/")
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:/", normalized):
        raise AuditError(f"absolute archive member path: {name}")
    parts = PurePosixPath(normalized).parts
    if ".." in parts:
        raise AuditError(f"path traversal archive member: {name}")
    if not parts or parts == (".",):
        raise AuditError(f"empty archive member path: {name}")
    return "/".join(part for part in parts if part != ".")


def _assert_allowed_member(name: str) -> str:
    normalized = _normalized_member_name(name)
    parts = PurePosixPath(normalized).parts
    if any(part in FORBIDDEN_COMPONENTS for part in parts):
        raise AuditError(f"forbidden archive member: {normalized}")
    if normalized.endswith(FORBIDDEN_SUFFIXES) or "/docs/superpowers/" in f"/{normalized}/":
        raise AuditError(f"forbidden archive member: {normalized}")
    return normalized


def _scan_member_text(member: str, content: bytes) -> None:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return
    findings = scan_text(member, text)
    if findings:
        raise AuditError(findings[0])


def _metadata_version(content: bytes) -> str:
    try:
        metadata = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise AuditError("wheel METADATA is not UTF-8") from error
    match = re.search(r"(?m)^Version:\s*(\S+)\s*$", metadata)
    if match is None:
        raise AuditError("wheel METADATA does not contain Version")
    return match.group(1)


def _wheel_version(filename: str) -> str:
    match = re.fullmatch(r"inferencefit-([^-]+)-[^-]+-[^-]+-[^-]+\.whl", filename)
    if match is None:
        raise AuditError(f"unexpected wheel filename: {filename}")
    return match.group(1)


def _sdist_version(filename: str) -> str:
    match = re.fullmatch(r"inferencefit-([^-]+)\.tar\.gz", filename)
    if match is None:
        raise AuditError(f"unexpected sdist filename: {filename}")
    return match.group(1)


def _assert_wheel_contents(path: Path, expected_version: str | None) -> int:
    required = set(WHEEL_REQUIRED_SUFFIXES)
    has_package_module = False
    metadata_version: str | None = None
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        for info in infos:
            name = _assert_allowed_member(info.filename)
            if info.is_dir():
                continue
            if name.startswith("inferencefit/") and name.endswith(".py"):
                has_package_module = True
            for suffix in tuple(required):
                if name.endswith(suffix):
                    required.remove(suffix)
                    if suffix.endswith("METADATA"):
                        metadata_version = _metadata_version(archive.read(info))
                    break
            _scan_member_text(name, archive.read(info))
    if not has_package_module:
        raise AuditError("wheel is missing package modules")
    if required:
        raise AuditError(f"wheel is missing required member: {sorted(required)[0]}")
    if metadata_version is None:
        raise AuditError("wheel is missing METADATA")
    filename_version = _wheel_version(path.name)
    assert_expected_version(filename_version, metadata_version)
    if expected_version is not None:
        assert_expected_version(expected_version, filename_version)
    return len(infos)


def _sdist_relative_name(name: str) -> str:
    parts = PurePosixPath(name).parts
    if len(parts) < 2:
        raise AuditError(f"sdist member lacks project root: {name}")
    return "/".join(parts[1:])


def _assert_sdist_contents(path: Path, expected_version: str | None) -> int:
    required = set(SDIST_REQUIRED_MEMBERS)
    has_tests = False
    with tarfile.open(path, "r:gz") as archive:
        members = archive.getmembers()
        for member in members:
            name = _assert_allowed_member(member.name)
            if not member.isfile():
                continue
            relative_name = _sdist_relative_name(name)
            required.discard(relative_name)
            has_tests = has_tests or relative_name.startswith("tests/")
            extracted = archive.extractfile(member)
            if extracted is None:
                raise AuditError(f"could not read archive member: {name}")
            _scan_member_text(name, extracted.read())
    if required:
        raise AuditError(f"sdist is missing required member: {sorted(required)[0]}")
    if not has_tests:
        raise AuditError("sdist is missing tests")
    filename_version = _sdist_version(path.name)
    if expected_version is not None:
        assert_expected_version(expected_version, filename_version)
    return len(members)


def _find_artifacts(dist_dir: Path) -> tuple[Path, Path]:
    wheels = sorted(dist_dir.glob("*.whl"))
    sdists = sorted(dist_dir.glob("*.tar.gz"))
    if len(wheels) != 1:
        raise AuditError(f"expected exactly one wheel, found {len(wheels)}")
    if len(sdists) != 1:
        raise AuditError(f"expected exactly one sdist, found {len(sdists)}")
    return wheels[0], sdists[0]


def audit_distribution(
    dist_dir: Path, expected_version: str | None = None
) -> list[ArtifactSummary]:
    """Audit the sole wheel and sdist in *dist_dir* without extracting them."""
    wheel, sdist = _find_artifacts(dist_dir)
    summaries = [
        ArtifactSummary(
            wheel.name, wheel.stat().st_size, _assert_wheel_contents(wheel, expected_version)
        ),
        ArtifactSummary(
            sdist.name, sdist.stat().st_size, _assert_sdist_contents(sdist, expected_version)
        ),
    ]
    return sorted(summaries, key=lambda summary: summary.name)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dist", type=Path, help="directory containing one wheel and one sdist")
    parser.add_argument("--expected-version", help="version expected from the release tag")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        summaries = audit_distribution(args.dist, args.expected_version)
    except (AuditError, OSError, tarfile.TarError, zipfile.BadZipFile) as error:
        print(f"audit failed: {error}", file=sys.stderr)
        return 1
    for summary in summaries:
        print(f"{summary.name}: {summary.size} bytes, {summary.member_count} members")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
