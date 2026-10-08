"""0.2.5 public guidance and backward-compatible release contracts."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_release_docs_cover_workspace_and_native_artifacts():
    notes = (ROOT / "docs" / "releases" / "0.2.5.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    contracts = (ROOT / "docs" / "contracts.md").read_text(encoding="utf-8")
    assert "## 0.2.5" in changelog
    assert "docs/releases/0.2.5.md" in changelog
    for content in (notes, readme, contracts):
        assert "ANTHROPIC_WORKSPACE_ID" in content
        assert "anthropic-workspace-id" in content
        assert "raw_response" in content
        assert "usage_details" in content
        assert "reasoning_tokens" in content
        assert "schema_version" in content or "schema version" in content
    assert "observations.jsonl" in notes
    assert "provider: claude" in notes


def test_historical_anthropic_release_notes_remain_available():
    assert (ROOT / "docs" / "releases" / "0.2.4.md").is_file()
    assert "## 0.2.4" in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
