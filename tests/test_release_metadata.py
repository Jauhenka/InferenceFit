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
    assert inferencefit.__version__ == "0.2.2"


@pytest.mark.parametrize(
    "required",
    [
        "InferenceFit 0.2.2",
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


@pytest.mark.parametrize(
    "required",
    [
        "pip install inferencefit",
        "inferencefit presets",
        "inferencefit init --preset structured-extraction ./eval",
        "inferencefit skill path",
        "coding",
        "document-processing",
        "structured-extraction",
        "representative production examples",
        "same core",
        "docs/releases/0.2.1.md",
        "docs/releases/0.2.0.md",
        "docs/releases/0.1.0.md",
    ],
)
def test_readme_documents_agent_ux_fast_path_and_history(required: str) -> None:
    assert required in (ROOT / "README.md").read_text(encoding="utf-8")


def test_agent_ux_release_notes_and_changelog_are_scoped() -> None:
    notes = ROOT / "docs" / "releases" / "0.2.1.md"
    assert notes.is_file()
    content = " ".join(notes.read_text(encoding="utf-8").lower().split())
    changelog = " ".join((ROOT / "CHANGELOG.md").read_text(encoding="utf-8").lower().split())

    for required in (
        "coding",
        "document-processing",
        "structured-extraction",
        "inferencefit presets",
        "inferencefit init",
        "inferencefit skill path",
        "non-overwrite",
        "schema_version",
        "provider",
        "engine",
        "semantic judge",
        "skill install",
    ):
        assert required in content
    assert "## 0.2.1" in changelog
    assert "docs/releases/0.2.1.md" in changelog
    assert "## 0.2.0" in changelog and "## 0.1.0" in changelog


def test_release_guide_uses_current_rehearsal_and_tag_examples() -> None:
    content = (ROOT / "docs" / "releasing.md").read_text(encoding="utf-8")
    assert "inferencefit==0.2.2" in content
    assert "v0.2.2" in content
    assert "READY_FOR_0.2.2" in content


def test_generic_provider_release_notes_and_changelog_are_scoped() -> None:
    notes = ROOT / "docs/releases/0.2.2.md"
    content = notes.read_text(encoding="utf-8").lower()
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8").lower()
    for required in (
        "provider: custom",
        "base_url",
        "credential_ref",
        "deprecated",
        "backward compatibility",
        "headers",
        "unknown cost",
        'schema_version: "0.1"',
    ):
        assert required in content
    assert "## 0.2.2" in changelog
    assert "docs/releases/0.2.2.md" in changelog
    for historical in ("0.1.0", "0.2.0", "0.2.1"):
        assert (ROOT / f"docs/releases/{historical}.md").is_file()


def test_packaged_skill_validator_reference_names_current_release() -> None:
    content = (ROOT / "src/inferencefit/skills/inferencefit/references/validators.md").read_text(
        encoding="utf-8"
    )
    assert "version 0.2.2 has no built-in semantic" in content


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
        "/.venv*",
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


def test_generic_provider_example_and_guidance_are_discoverable() -> None:
    from inferencefit.spec import load_evaluation_spec

    example_dir = ROOT / "examples" / "generic_openai_compatible"
    spec_path = example_dir / "eval.yaml"
    loaded = load_evaluation_spec(spec_path)
    candidate = loaded.spec.candidates[0]
    assert len(loaded.spec.candidates) == 1
    assert candidate.provider == "custom"
    assert candidate.model == "some/model-name"
    assert candidate.base_url == "https://api.example.com/v1"
    assert candidate.credential_ref == "example-main"
    assert len(loaded.resolve_dataset_path().read_text(encoding="utf-8").splitlines()) == 1

    readme = (ROOT / "README.md").read_text(encoding="utf-8").lower()
    contracts = (ROOT / "docs/contracts.md").read_text(encoding="utf-8").lower()
    index = (ROOT / "examples/README.md").read_text(encoding="utf-8")
    example_readme = (example_dir / "README.md").read_text(encoding="utf-8").lower()
    assert "generic_openai_compatible" in index
    for text in (readme, contracts, example_readme):
        assert "provider: custom" in text
        assert "base_url" in text
        assert "inferencefit_credential_example_main" in text
        assert "localhost" in text or "127.0.0.1" in text
        assert "unknown" in text and "cost" in text
        assert "deprecated" in text and "backward compatibility" in text
    assert "first-class" in readme
    assert "stream" in contracts
    assert "example.com" in spec_path.read_text(encoding="utf-8")
