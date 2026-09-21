import tomllib
from pathlib import Path

import inferencefit

ROOT = Path(__file__).resolve().parents[1]


def load_pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_release_version_has_one_maintained_source() -> None:
    config = load_pyproject()
    assert "version" not in config["project"]
    assert config["project"]["dynamic"] == ["version"]
    assert config["tool"]["hatch"]["version"]["path"] == "src/inferencefit/__init__.py"
    assert inferencefit.__version__ == "0.1.0"


def test_public_package_metadata_is_complete() -> None:
    project = load_pyproject()["project"]
    assert project["name"] == "inferencefit"
    assert project["license"] == "Apache-2.0"
    assert project["license-files"] == ["LICENSE"]
    assert project["requires-python"] == ">=3.11"
    assert project["urls"]["Repository"] == "https://github.com/Jauhenka/InferenceFit"
    assert project["urls"]["Issues"] == "https://github.com/Jauhenka/InferenceFit/issues"
    assert "twine>=5.1" in project["optional-dependencies"]["dev"]


def test_classifiers_and_runtime_dependencies_are_scoped() -> None:
    project = load_pyproject()["project"]
    classifiers = set(project["classifiers"])
    assert "Programming Language :: Python :: 3.11" in classifiers
    assert "Programming Language :: Python :: 3.12" in classifiers
    assert "Programming Language :: Python :: 3.13" in classifiers
    assert "License :: OSI Approved :: Apache Software License" in classifiers
    assert "Operating System :: OS Independent" in classifiers
    runtime_dependencies = set(project["dependencies"])
    for package in ("pytest", "ruff", "build", "twine"):
        assert not any(
            dependency.lower().startswith(package) for dependency in runtime_dependencies
        )


def test_gitignore_covers_release_local_state() -> None:
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    normalized = {line.strip().rstrip("/") for line in ignored if line.strip()}
    required = {
        ".inferencefit",
        ".venv",
        "dist",
        "build",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".env*",
        "/.vs",
    }
    assert required <= normalized


def test_sdist_excludes_internal_and_local_state() -> None:
    excluded = set(load_pyproject()["tool"]["hatch"]["build"]["targets"]["sdist"]["exclude"])
    required = {
        "/.github",
        "/.inferencefit",
        "/.superpowers",
        "/.venv",
        "/AGENTS.md",
        "/docs/superpowers",
        "/dist",
    }
    assert required <= excluded
