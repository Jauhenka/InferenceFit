from __future__ import annotations

import tarfile
import warnings
import zipfile
from io import BytesIO
from pathlib import Path
from stat import S_IFIFO, S_IFLNK

import pytest
from scripts import audit_distribution as audit

WHEEL_NAME = "inferencefit-0.1.0-py3-none-any.whl"
SDIST_NAME = "inferencefit-0.1.0.tar.gz"

PACKAGE_RESOURCE_MEMBERS = (
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
)


def write_wheel(
    path: Path,
    extra_members: dict[str, str | bytes] | None = None,
    *,
    dist_info: str = "inferencefit-0.1.0.dist-info",
    metadata_name: str = "inferencefit",
    metadata_version: str = "0.1.0",
    with_directories: bool = False,
    omit_members: set[str] | None = None,
) -> None:
    members = {
        "inferencefit/__init__.py": '__version__ = "0.1.0"\n',
        f"{dist_info}/METADATA": (
            f"Metadata-Version: 2.1\nName: {metadata_name}\nVersion: {metadata_version}\n"
        ),
        f"{dist_info}/WHEEL": "Wheel-Version: 1.0\nTag: py3-none-any\n",
        f"{dist_info}/licenses/LICENSE": "Apache License\n",
        f"{dist_info}/entry_points.txt": (
            "[console_scripts]\ninferencefit = inferencefit.cli:app\n"
        ),
    }
    members.update(
        {
            f"inferencefit/{name}": f"packaged resource: {name}\n"
            for name in PACKAGE_RESOURCE_MEMBERS
        }
    )
    members.update(extra_members or {})
    for name in omit_members or set():
        members.pop(name, None)
    with zipfile.ZipFile(path, "w") as archive:
        if with_directories:
            for directory in ("inferencefit", dist_info):
                archive.writestr(f"{directory}/", "")
        for name, content in members.items():
            archive.writestr(name, content)


def write_sdist(
    path: Path,
    *,
    root: str = "inferencefit-0.1.0",
    pkg_info: str = "Metadata-Version: 2.1\nName: inferencefit\nVersion: 0.1.0\n",
    extra_members: dict[str, str | bytes] | None = None,
    link_target: str | None = None,
    hardlink_target: str | None = None,
    with_directories: bool = False,
    omit_members: set[str] | None = None,
) -> None:
    members = {
        "PKG-INFO": pkg_info,
        "pyproject.toml": "[project]\nname = 'inferencefit'\n",
        "README.md": "# InferenceFit\n",
        "LICENSE": "Apache License\n",
        "CHANGELOG.md": "# Changelog\n",
        "src/inferencefit/__init__.py": '__version__ = "0.1.0"\n',
        "tests/test_smoke.py": "def test_smoke(): pass\n",
    }
    members.update(
        {
            f"src/inferencefit/{name}": f"packaged resource: {name}\n"
            for name in PACKAGE_RESOURCE_MEMBERS
        }
    )
    members.update(extra_members or {})
    for name in omit_members or set():
        members.pop(name, None)
    with tarfile.open(path, "w:gz") as archive:
        if with_directories:
            for directory in ("", "src", "src/inferencefit", "tests"):
                info = tarfile.TarInfo(f"{root}/{directory}".rstrip("/"))
                info.type = tarfile.DIRTYPE
                archive.addfile(info)
        for name, content in members.items():
            encoded = content.encode()
            info = tarfile.TarInfo(f"{root}/{name}")
            info.size = len(encoded)
            archive.addfile(info, BytesIO(encoded))
        if link_target is not None:
            link = tarfile.TarInfo(f"{root}/link")
            link.type = tarfile.SYMTYPE
            link.linkname = link_target
            archive.addfile(link)
        if hardlink_target is not None:
            hardlink = tarfile.TarInfo(f"{root}/hardlink")
            hardlink.type = tarfile.LNKTYPE
            hardlink.linkname = hardlink_target
            archive.addfile(hardlink)


def write_valid_distribution(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    dist.mkdir()
    write_wheel(dist / WHEEL_NAME)
    write_sdist(dist / SDIST_NAME)
    return dist


@pytest.mark.parametrize("artifact", ["wheel", "sdist"])
@pytest.mark.parametrize("resource", PACKAGE_RESOURCE_MEMBERS)
def test_packaged_resource_is_required(
    tmp_path: Path, artifact: str, resource: str
) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    wheel_member = f"inferencefit/{resource}"
    sdist_member = f"src/inferencefit/{resource}"
    write_wheel(
        dist / WHEEL_NAME,
        omit_members={wheel_member} if artifact == "wheel" else None,
    )
    write_sdist(
        dist / SDIST_NAME,
        omit_members={sdist_member} if artifact == "sdist" else None,
    )

    with pytest.raises(audit.AuditError, match="missing required member"):
        audit.audit_distribution(dist, expected_version="0.1.0")


@pytest.mark.parametrize(
    "member",
    [
        "pkg/.env",
        "pkg/.inferencefit/runs/run/result.json",
        "pkg/.mypy_cache/3.14/cache.json",
        "pkg/.nox/tests/pyvenv.cfg",
        "pkg/.ruff_cache/content",
        "pkg/.superpowers/sdd/progress.md",
        "pkg/.tox/py311/pyvenv.cfg",
        "pkg/.venv/pyvenv.cfg",
        "pkg/.pytest_cache/v/cache/nodeids",
        "pkg/venv/pyvenv.cfg",
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


@pytest.mark.parametrize(
    "member",
    [
        r"C:\\release\\outside.txt",
        r"C:..\\outside.txt",
        r"\\rooted\\outside.txt",
        r"pkg\\..\\outside.txt",
    ],
)
def test_windows_and_backslash_traversal_members_are_rejected(tmp_path: Path, member: str) -> None:
    dist = write_valid_distribution(tmp_path)
    write_wheel(dist / WHEEL_NAME, {member: "escape\n"})

    with pytest.raises(audit.AuditError, match="absolute|traversal|drive"):
        audit.audit_distribution(dist, expected_version="0.1.0")


def test_secret_like_content_is_rejected() -> None:
    credential = "Bearer " + "abcdefghijklmnopqrstuvwxyz" + "123456"
    findings = audit.scan_text("config.txt", credential)

    assert findings


@pytest.mark.parametrize(
    "value",
    [
        "OPENAI_API_KEY=your-api-key-here",
        "OPENAI_API_KEY=dummy",
        "sk-example123456",
        'DEEPSEEK_API_KEY = "your-api-key-here"',
        "OPENROUTER_API_KEY='placeholder'",
        "OPEN_ROUTER_API_KEY='placeholder'",
        'GEMINI_API_KEY = "your-api-key-here"',
        'INFERENCEFIT_CREDENTIAL_ROUTER_TOKEN = "redacted"',
    ],
)
def test_documented_secret_placeholders_are_not_rejected(value: str) -> None:
    assert audit.scan_text("docs/config.md", value) == []


def test_distribution_audit_test_source_does_not_package_secret_like_content() -> None:
    source = Path(__file__).read_text(encoding="utf-8")

    assert audit.scan_text(Path(__file__).name, source) == []


def test_provider_key_assignment_is_rejected_from_archive(tmp_path: Path) -> None:
    dist = write_valid_distribution(tmp_path)
    credential = "OPENAI_API_KEY=" + "sk-" + "secretvalue\n"
    write_wheel(dist / WHEEL_NAME, {"inferencefit/settings.py": credential})

    with pytest.raises(audit.AuditError, match="secret-like"):
        audit.audit_distribution(dist, expected_version="0.1.0")


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("DEEPSEEK" + "_API_KEY", "deepseek-real-secret-value-123456"),
        ("OPENROUTER" + "_API_KEY", "openrouter-real-secret-value-123456"),
        ("OPEN_ROUTER" + "_API_KEY", "router-real-secret-value-123456"),
        ("GEMINI" + "_API_KEY", "gemini-real-secret-value-123456"),
        ("OPENAI" + "_API_KEY", "openai-real-secret-value-123456"),
        (
            "INFERENCEFIT" + "_CREDENTIAL_ROUTER_TOKEN",
            "router-real-secret-value-123456",
        ),
    ],
)
@pytest.mark.parametrize("artifact", ["wheel", "sdist"])
def test_release_credential_assignment_is_rejected_from_archive(
    tmp_path: Path, name: str, value: str, artifact: str
) -> None:
    dist = write_valid_distribution(tmp_path)
    credential = f'{name} = "{value}"\n'
    if artifact == "wheel":
        write_wheel(dist / WHEEL_NAME, {"inferencefit/settings.py": credential})
    else:
        write_sdist(dist / SDIST_NAME, extra_members={"src/inferencefit/settings.py": credential})

    with pytest.raises(audit.AuditError, match="secret-like"):
        audit.audit_distribution(dist, expected_version="0.1.0")


def test_release_credential_assignment_crossing_scan_chunk_is_rejected(
    tmp_path: Path,
) -> None:
    dist = write_valid_distribution(tmp_path)
    prefix = "x" * (audit.SCAN_CHUNK_BYTES - len("OPENROUTER_API") - 1) + "\n"
    credential_name = "OPENROUTER" + "_API_KEY"
    credential = prefix + f'{credential_name} = "real-secret-value-123456"\n'
    write_wheel(dist / WHEEL_NAME, {"inferencefit/settings.py": credential})

    with pytest.raises(audit.AuditError, match="secret-like"):
        audit.audit_distribution(dist, expected_version="0.1.0")


def test_mixed_decode_secret_content_is_rejected_from_archive(tmp_path: Path) -> None:
    dist = write_valid_distribution(tmp_path)
    credential = b"\xffOPENAI_API_KEY=" + b"real-" + b"secret-value-123456\n"
    write_wheel(
        dist / WHEEL_NAME,
        {"inferencefit/settings.py": credential},
    )

    with pytest.raises(audit.AuditError, match="secret-like"):
        audit.audit_distribution(dist, expected_version="0.1.0")


def test_wheel_requires_exact_dist_info_identity_and_metadata_name(tmp_path: Path) -> None:
    dist = write_valid_distribution(tmp_path)
    write_wheel(
        dist / WHEEL_NAME,
        dist_info="other-0.1.0.dist-info",
        metadata_name="other",
    )

    with pytest.raises(audit.AuditError, match="dist-info|Name"):
        audit.audit_distribution(dist, expected_version="0.1.0")


def test_wheel_metadata_version_must_match_filename(tmp_path: Path) -> None:
    dist = write_valid_distribution(tmp_path)
    write_wheel(dist / WHEEL_NAME, metadata_version="0.1.1")

    with pytest.raises(audit.AuditError, match="Version|expected version"):
        audit.audit_distribution(dist, expected_version="0.1.0")


def test_sdist_root_and_pkg_info_identity_must_match_filename(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    write_wheel(dist / WHEEL_NAME)
    write_sdist(
        dist / SDIST_NAME,
        root="inferencefit-0.1.1",
        pkg_info="Metadata-Version: 2.1\nName: other\nVersion: 0.1.1\n",
    )

    with pytest.raises(audit.AuditError, match="root|Name|expected version"):
        audit.audit_distribution(dist, expected_version="0.1.0")


def test_duplicate_normalized_member_is_rejected(tmp_path: Path) -> None:
    dist = write_valid_distribution(tmp_path)
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Duplicate name: .*", category=UserWarning)
        with zipfile.ZipFile(dist / WHEEL_NAME, "a") as archive:
            archive.writestr(r"inferencefit-0.1.0.dist-info\METADATA", "Name: inferencefit\n")

    with pytest.raises(audit.AuditError, match="duplicate normalized archive member"):
        audit.audit_distribution(dist, expected_version="0.1.0")


def test_zip_symlink_like_member_is_rejected(tmp_path: Path) -> None:
    dist = write_valid_distribution(tmp_path)
    with zipfile.ZipFile(dist / WHEEL_NAME, "a") as archive:
        link = zipfile.ZipInfo("inferencefit/link")
        link.external_attr = S_IFLNK << 16
        archive.writestr(link, "../../outside")

    with pytest.raises(audit.AuditError, match="symlink"):
        audit.audit_distribution(dist, expected_version="0.1.0")


def test_zip_special_member_is_rejected(tmp_path: Path) -> None:
    dist = write_valid_distribution(tmp_path)
    with zipfile.ZipFile(dist / WHEEL_NAME, "a") as archive:
        special = zipfile.ZipInfo("inferencefit/fifo")
        special.create_system = 3
        special.external_attr = S_IFIFO << 16
        archive.writestr(special, "")

    with pytest.raises(audit.AuditError, match="special"):
        audit.audit_distribution(dist, expected_version="0.1.0")


def test_tar_link_member_is_rejected(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    write_wheel(dist / WHEEL_NAME)
    write_sdist(dist / SDIST_NAME, link_target="../../outside")

    with pytest.raises(audit.AuditError, match="link|special"):
        audit.audit_distribution(dist, expected_version="0.1.0")


def test_tar_hardlink_member_is_rejected(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    write_wheel(dist / WHEEL_NAME)
    write_sdist(dist / SDIST_NAME, hardlink_target="README.md")

    with pytest.raises(audit.AuditError, match="link|special"):
        audit.audit_distribution(dist, expected_version="0.1.0")


def test_directory_entries_are_accepted(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    write_wheel(dist / WHEEL_NAME, with_directories=True)
    write_sdist(dist / SDIST_NAME, with_directories=True)

    results = audit.audit_distribution(dist, expected_version="0.1.0")

    assert len(results) == 2


@pytest.mark.parametrize(
    ("attribute", "value", "extra_members", "match"),
    [
        ("MAX_MEMBER_COUNT", 4, {}, "member count"),
        ("MAX_MEMBER_UNCOMPRESSED_BYTES", 1, {"inferencefit/large.py": "abc"}, "member size"),
        ("MAX_TOTAL_UNCOMPRESSED_BYTES", 1, {}, "total size"),
    ],
)
def test_wheel_resource_bounds_are_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    attribute: str,
    value: int,
    extra_members: dict[str, str],
    match: str,
) -> None:
    dist = write_valid_distribution(tmp_path)
    write_wheel(dist / WHEEL_NAME, extra_members)
    monkeypatch.setattr(audit, attribute, value)

    with pytest.raises(audit.AuditError, match=match):
        audit.audit_distribution(dist, expected_version="0.1.0")


def test_wheel_compression_ratio_bound_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dist = write_valid_distribution(tmp_path)
    with zipfile.ZipFile(dist / WHEEL_NAME, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("inferencefit/__init__.py", "x" * 1_000)
        archive.writestr(
            "inferencefit-0.1.0.dist-info/METADATA",
            "Metadata-Version: 2.1\nName: inferencefit\nVersion: 0.1.0\n",
        )
        archive.writestr("inferencefit-0.1.0.dist-info/WHEEL", "Wheel-Version: 1.0\n")
        archive.writestr("inferencefit-0.1.0.dist-info/entry_points.txt", "")
        archive.writestr("inferencefit-0.1.0.dist-info/licenses/LICENSE", "license\n")
    monkeypatch.setattr(audit, "MAX_COMPRESSION_RATIO", 1.0)

    with pytest.raises(audit.AuditError, match="compression ratio"):
        audit.audit_distribution(dist, expected_version="0.1.0")


def test_sdist_compression_ratio_bound_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    write_wheel(dist / WHEEL_NAME)
    write_sdist(
        dist / SDIST_NAME,
        extra_members={"docs/repeated.txt": "x" * 100_000},
    )
    monkeypatch.setattr(audit, "MAX_COMPRESSION_RATIO", 10.0)

    with pytest.raises(audit.AuditError, match="compression ratio"):
        audit.audit_distribution(dist, expected_version="0.1.0")


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
    assert any(
        line.startswith(f"{SDIST_NAME}: ") and "bytes, 23 members" in line for line in output
    )
    assert any(
        line.startswith(f"{WHEEL_NAME}: ") and "bytes, 21 members" in line for line in output
    )
