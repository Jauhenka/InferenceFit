"""0.2.4 Anthropic guidance and installed dispatch contracts."""

from pathlib import Path

from inferencefit.spec import load_evaluation_spec

ROOT = Path(__file__).resolve().parents[1]


def test_anthropic_example_is_discoverable_and_bounded():
    directory = ROOT / "examples" / "anthropic"
    loaded = load_evaluation_spec(directory / "eval.yaml")
    candidate = loaded.spec.candidates[0]
    assert candidate.provider == "anthropic"
    assert candidate.base_url is None
    assert candidate.model == "<claude-model-id>"
    assert candidate.parameters["max_tokens"] == 64
    assert len(loaded.resolve_dataset_path().read_text(encoding="utf-8").splitlines()) == 1
    assert "ANTHROPIC_API_KEY" in (directory / "README.md").read_text(encoding="utf-8")
    for path in (
        ROOT / "README.md",
        ROOT / "docs" / "contracts.md",
        ROOT / "examples" / "README.md",
        ROOT / "src" / "inferencefit" / "skills" / "inferencefit" / "SKILL.md",
    ):
        content = path.read_text(encoding="utf-8")
        assert "Anthropic" in content
        assert "provider: anthropic" in content
        assert "provider: claude" in content


def test_release_notes_and_installed_dispatch_contract():
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    notes = (ROOT / "docs" / "releases" / "0.2.4.md").read_text(encoding="utf-8")
    assert "## 0.2.4" in changelog
    assert "docs/releases/0.2.4.md" in changelog
    for required in ("ANTHROPIC_API_KEY", "provider: anthropic", "provider: claude", "0.1"):
        assert required in notes
    from scripts.installed_distribution_smoke import assert_anthropic_profiles

    assert assert_anthropic_profiles() == {
        "anthropic": "AnthropicProvider",
        "claude": "AnthropicProvider",
    }
