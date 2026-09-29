"""Inspect release archives without extracting their untrusted members."""

from __future__ import annotations

import argparse
import re
import stat
import sys
import tarfile
import zipfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
from pathlib import Path
from typing import BinaryIO


class AuditError(ValueError):
    """A distribution archive does not meet the release policy."""


@dataclass(frozen=True)
class ArtifactSummary:
    name: str
    size: int
    member_count: int


MAX_MEMBER_COUNT = 10_000
MAX_MEMBER_UNCOMPRESSED_BYTES = 10 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100.0
SCAN_CHUNK_BYTES = 64 * 1024
SCAN_OVERLAP_CHARS = 512
FORBIDDEN_COMPONENTS = frozenset(
    {
        ".coverage",
        ".env",
        ".github",
        ".inferencefit",
        ".mypy_cache",
        ".nox",
        ".pytest_cache",
        ".ruff_cache",
        ".superpowers",
        ".tox",
        ".venv",
        "__pycache__",
        "AGENTS.md",
        "venv",
    }
)
FORBIDDEN_SUFFIXES = (".pyc",)
PLACEHOLDER_MARKERS = (
    "example",
    "dummy",
    "placeholder",
    "redacted",
    "your-api-key",
    "your_api_key",
    "changeme",
)
SECRET_PATTERNS = (
    re.compile(r"(?i)\bbearer\s+(?P<value>[a-z0-9._~+/=-]{20,})"),
    re.compile(r"\b(?P<value>sk-[A-Za-z0-9_-]{8,})"),
    re.compile(
        r"(?im)\b(?:(?:OPENAI|ANTHROPIC|FIREWORKS|AZURE|GOOGLE|AWS|DEEPSEEK|OPENROUTER)_"
        r"(?:API_)?(?:KEY|TOKEN|SECRET)|OPEN_ROUTER_API_KEY|GEMINI_API_KEY|"
        r"INFERENCEFIT_CREDENTIAL_[A-Z0-9_]+)"
        r"\s*=\s*['\"]?(?P<value>[^\s'\"]+)"
    ),
)
PACKAGE_RESOURCE_MEMBERS = frozenset(
    {
        "presets/templates/coding/README.md",
        "presets/templates/coding/cases.jsonl",
        "presets/templates/coding/eval.yaml",
        "presets/templates/coding/fixtures/sample.jsonl",
        "presets/templates/document-processing/README.md",
        "presets/templates/document-processing/cases.jsonl",
        "presets/templates/document-processing/eval.yaml",
        "presets/templates/document-processing/fixtures/sample.jsonl",
        "presets/templates/structured-extraction/README.md",
        "presets/templates/structured-extraction/cases.jsonl",
        "presets/templates/structured-extraction/eval.yaml",
        "presets/templates/structured-extraction/fixtures/sample.jsonl",
        "skills/inferencefit/SKILL.md",
        "skills/inferencefit/references/interpreting-results.md",
        "skills/inferencefit/references/presets.md",
        "skills/inferencefit/references/validators.md",
    }
)
WHEEL_PACKAGE_REQUIRED_MEMBERS = frozenset(
    f"inferencefit/{name}" for name in PACKAGE_RESOURCE_MEMBERS
)
SDIST_REQUIRED_MEMBERS = frozenset(
    {
        "pyproject.toml",
        "README.md",
        "LICENSE",
        "CHANGELOG.md",
        "src/inferencefit/__init__.py",
        *(f"src/inferencefit/{name}" for name in PACKAGE_RESOURCE_MEMBERS),
    }
)


def scan_text(member: str, text: str) -> list[str]:
    findings = []
    for pattern in SECRET_PATTERNS:
        for match in pattern.finditer(text):
            if not any(marker in match.group("value").lower() for marker in PLACEHOLDER_MARKERS):
                findings.append(f"{member}: secret-like content")
    return findings


def assert_expected_version(expected: str, actual: str) -> None:
    if expected != actual:
        raise AuditError(f"expected version {expected}, found {actual}")


def _normalized_project_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def _member_name(raw: str) -> str:
    name = raw.replace("\\", "/")
    # Directory entries (ZIP always, TAR sometimes) carry a trailing slash.
    name = name.removesuffix("/")
    if not name:
        raise AuditError(f"empty archive member path: {raw}")
    if name.startswith("/"):
        raise AuditError(f"absolute archive member path: {raw}")
    if re.match(r"^[A-Za-z]:", name):
        raise AuditError(f"drive archive member path: {raw}")
    parts = name.split("/")
    if any(part == ".." for part in parts):
        raise AuditError(f"path traversal archive member: {raw}")
    if any(not part or part == "." for part in parts):
        raise AuditError(f"invalid archive member path: {raw}")
    if (
        any(part in FORBIDDEN_COMPONENTS for part in parts)
        or name.endswith(FORBIDDEN_SUFFIXES)
        or "/docs/superpowers/" in f"/{name}/"
    ):
        raise AuditError(f"forbidden archive member: {name}")
    return name


def _unique_names(raw_names: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen = set()
    for raw_name in raw_names:
        name = _member_name(raw_name)
        if name in seen:
            raise AuditError(f"duplicate normalized archive member: {name}")
        seen.add(name)
        result.append(name)
    return result


def _check_compression_ratio(uncompressed: int, compressed: int) -> None:
    if uncompressed / max(compressed, 1) > MAX_COMPRESSION_RATIO:
        raise AuditError("compression ratio exceeds limit")


def _resource_bounds(sizes: Iterable[int], compressed_sizes: Iterable[int] | None = None) -> None:
    sizes = list(sizes)
    if len(sizes) > MAX_MEMBER_COUNT:
        raise AuditError(f"member count exceeds limit: {len(sizes)}")
    if any(size > MAX_MEMBER_UNCOMPRESSED_BYTES for size in sizes):
        raise AuditError("member size exceeds limit")
    if sum(sizes) > MAX_TOTAL_UNCOMPRESSED_BYTES:
        raise AuditError("total size exceeds limit")
    if compressed_sizes is not None:
        for size, compressed in zip(sizes, compressed_sizes, strict=True):
            _check_compression_ratio(size, compressed)


def _scan_stream(member: str, stream: BinaryIO) -> None:
    tail = ""
    while chunk := stream.read(SCAN_CHUNK_BYTES):
        text = tail + chunk.decode("utf-8", errors="replace")
        if findings := scan_text(member, text):
            raise AuditError(findings[0])
        tail = text[-SCAN_OVERLAP_CHARS:]


def _parse_metadata(content: bytes, label: str) -> tuple[str, str]:
    message = BytesParser(policy=policy.default).parsebytes(content)
    name, version = message.get("Name"), message.get("Version")
    if not name or not version:
        raise AuditError(f"{label} must contain Name and Version")
    return name, version


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


def _audit_wheel(path: Path, expected_version: str | None) -> int:
    version = _wheel_version(path.name)
    dist_info = f"inferencefit-{version}.dist-info"
    required = {
        f"{dist_info}/METADATA",
        f"{dist_info}/WHEEL",
        f"{dist_info}/entry_points.txt",
        f"{dist_info}/licenses/LICENSE",
        "inferencefit/__init__.py",
    } | set(WHEEL_PACKAGE_REQUIRED_MEMBERS)
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        names = _unique_names(info.filename for info in infos)
        _resource_bounds((info.file_size for info in infos), (info.compress_size for info in infos))
        metadata = None
        for info, name in zip(infos, names, strict=True):
            file_type = stat.S_IFMT(info.external_attr >> 16)
            if file_type == stat.S_IFLNK:
                raise AuditError(f"symlink archive member: {name}")
            if file_type not in (0, stat.S_IFREG, stat.S_IFDIR):
                raise AuditError(f"special archive member: {name}")
            if info.is_dir() or file_type == stat.S_IFDIR:
                continue
            required.discard(name)
            with archive.open(info) as stream:
                content = stream.read() if name == f"{dist_info}/METADATA" else None
                if content is not None:
                    metadata = content
                    _scan_stream(name, _BytesReader(content))
                else:
                    _scan_stream(name, stream)
    if required:
        raise AuditError(f"wheel is missing required member: {min(required)}")
    if metadata is None:
        raise AuditError("wheel is missing METADATA")
    name, metadata_version = _parse_metadata(metadata, "wheel METADATA")
    if _normalized_project_name(name) != "inferencefit":
        raise AuditError(f"wheel METADATA Name is not inferencefit: {name}")
    assert_expected_version(version, metadata_version)
    if expected_version is not None:
        assert_expected_version(expected_version, version)
    return len(infos)


class _BytesReader:
    def __init__(self, content: bytes) -> None:
        self.content, self.offset = content, 0

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self.content) - self.offset
        result = self.content[self.offset : self.offset + size]
        self.offset += len(result)
        return result


def _audit_sdist(path: Path, expected_version: str | None) -> int:
    version = _sdist_version(path.name)
    root = f"inferencefit-{version}"
    required, has_tests, pkg_info = set(SDIST_REQUIRED_MEMBERS), False, None
    with tarfile.open(path, "r:gz") as archive:
        members = archive.getmembers()
        names = _unique_names(member.name for member in members)
        _resource_bounds(member.size for member in members)
        _check_compression_ratio(sum(member.size for member in members), path.stat().st_size)
        for member, name in zip(members, names, strict=True):
            if not (member.isfile() or member.isdir()):
                raise AuditError(f"link or special archive member: {name}")
            parts = name.split("/")
            if parts[0] != root:
                raise AuditError(f"sdist root must be {root}: {name}")
            if member.isdir():
                continue
            relative = "/".join(parts[1:])
            required.discard(relative)
            has_tests = has_tests or relative.startswith("tests/")
            stream = archive.extractfile(member)
            if stream is None:
                raise AuditError(f"could not read archive member: {name}")
            content = stream.read() if relative == "PKG-INFO" else None
            if content is not None:
                pkg_info = content
                _scan_stream(name, _BytesReader(content))
            else:
                _scan_stream(name, stream)
    if required:
        raise AuditError(f"sdist is missing required member: {min(required)}")
    if not has_tests:
        raise AuditError("sdist is missing tests")
    if pkg_info is None:
        raise AuditError("sdist is missing PKG-INFO")
    name, package_version = _parse_metadata(pkg_info, "sdist PKG-INFO")
    if _normalized_project_name(name) != "inferencefit":
        raise AuditError(f"sdist PKG-INFO Name is not inferencefit: {name}")
    assert_expected_version(version, package_version)
    if expected_version is not None:
        assert_expected_version(expected_version, version)
    return len(members)


def audit_distribution(
    dist_dir: Path, expected_version: str | None = None
) -> list[ArtifactSummary]:
    wheels, sdists = sorted(dist_dir.glob("*.whl")), sorted(dist_dir.glob("*.tar.gz"))
    if len(wheels) != 1:
        raise AuditError(f"expected exactly one wheel, found {len(wheels)}")
    if len(sdists) != 1:
        raise AuditError(f"expected exactly one sdist, found {len(sdists)}")
    wheel, sdist = wheels[0], sdists[0]
    return sorted(
        [
            ArtifactSummary(
                wheel.name, wheel.stat().st_size, _audit_wheel(wheel, expected_version)
            ),
            ArtifactSummary(
                sdist.name, sdist.stat().st_size, _audit_sdist(sdist, expected_version)
            ),
        ],
        key=lambda summary: summary.name,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dist", type=Path)
    parser.add_argument("--expected-version")
    args = parser.parse_args(argv)
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
