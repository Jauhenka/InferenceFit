import tomllib
from pathlib import Path

import pytest

import inferencefit

ROOT = Path(__file__).resolve().parents[1]


def load_pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_default_pytest_run_excludes_live_provider_requests() -> None:
    addopts = load_pyproject()["tool"]["pytest"]["ini_options"]["addopts"]
    assert "not provider_live" in addopts


def test_release_version_has_one_maintained_source() -> None:
    config = load_pyproject()
    assert "version" not in config["project"]
    assert config["project"]["dynamic"] == ["version"]
    assert config["tool"]["hatch"]["version"]["path"] == "src/inferencefit/__init__.py"
    assert inferencefit.__version__ == "0.2.0"


@pytest.mark.parametrize(
    "required",
    [
        "InferenceFit 0.2.0",
        "Fireworks",
        "DeepSeek",
        "OpenRouter",
        "Gemini",
        "OpenAI",
        "fixture",
        "Ollama",
        "vLLM",
        "custom",
        "OPEN_ROUTER_API_KEY",
        "GEMINI_API_KEY",
        "OPENAI_API_KEY",
        "provider: openrouter",
        "provider: gemini",
        "provider: openai",
        "max_output_tokens",
        "python -m pytest tests/test_provider_live.py -m provider_live -q",
        "supported parameters",
        "eval.openrouter.smoke.yaml",
        "eval.gemini.smoke.yaml",
        "eval.openai.smoke.yaml",
    ],
)
def test_readme_documents_multi_provider_release(required: str) -> None:
    assert required in (ROOT / "README.md").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "field",
    [
        "provider",
        "model",
        "provider_backend",
        "cost_source",
        "total_tokens",
        "provider_reported",
    ],
)
def test_contract_docs_explain_additive_optional_release_fields(field: str) -> None:
    content = (ROOT / "docs/contracts.md").read_text(encoding="utf-8")
    assert 'schema_version: "0.1"' in content
    assert "0.2.0" in content
    assert "optional" in content
    assert field in content


def test_multi_provider_release_notes_and_changelog_exist() -> None:
    notes = ROOT / "docs/releases/0.2.0.md"
    assert notes.is_file()
    content = notes.read_text(encoding="utf-8")
    for required in ("0.2.0", "OpenRouter", "Gemini", "OpenAI", "0.1"):
        assert required in content
    for field in ("provider", "model", "provider_backend", "cost_source", "usage.total_tokens"):
        assert f"`{field}`" in content
    assert "## 0.2.0" in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")


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


def test_sdist_excludes_internal_release_planning_documents() -> None:
    excluded = set(load_pyproject()["tool"]["hatch"]["build"]["targets"]["sdist"]["exclude"])
    required = {
        "/docs/implementation-plan.md",
        "/docs/release-0.1.0.md",
    }
    assert required <= excluded
