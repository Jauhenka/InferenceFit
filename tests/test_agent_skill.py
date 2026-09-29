"""Contract tests for the packaged, vendor-neutral InferenceFit Agent Skill.

These tests audit the canonical skill directory that ships as package data. They
assert structural invariants (frontmatter, folder/name agreement, concise body,
one-level references, valid links) and the meaningful content invariants the spec
requires, without pinning the full prose of any document.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

import inferencefit

SKILL_DIR = Path(inferencefit.__file__).resolve().parent / "skills" / "inferencefit"
SKILL_FILE = SKILL_DIR / "SKILL.md"
REFERENCES_DIR = SKILL_DIR / "references"

EXPECTED_REFERENCE_FILES = {
    "presets.md",
    "validators.md",
    "interpreting-results.md",
}
EXPECTED_REFERENCE_LINKS = {
    "references/presets.md",
    "references/validators.md",
    "references/interpreting-results.md",
}
EXPECTED_PRESET_IDS = [
    "coding",
    "document-processing",
    "structured-extraction",
]

# The only registered CLI sub-commands an agent may be told to run in the skill.
KNOWN_CLI_SUBCOMMANDS = {"presets", "init", "validate", "benchmark", "serve", "skill"}
# Neutral words that legitimately follow the word "inferencefit" but are not commands.
NON_COMMAND_FOLLOWERS = {
    "command",
    "commands",
    "cli",
    "description",
    "package",
    "project",
    "yaml",
    "spec",
}

MARKDOWN_LINK = re.compile(r"\]\(([^)\s]+)\)")
CLI_INVOCATION = re.compile(r"inferencefit\s+([a-z][a-z0-9-]*)")
SECRET_ASSIGNMENT = re.compile(
    r"(?i)(?:api[_-]?key|access[_-]?token|secret|password)\s*[:=]\s*[\"'][^\"']+[\"']"
)
LIVE_MODEL_IDENTIFIERS = {
    "accounts/fireworks/models/nemotron-lightning-3p5-30b-a3b",
    "deepseek-flash",
    "gemini-3.5-flash-lite",
    "gpt-6-luna",
    "openrouter/free",
}
MODEL_NAME_PATTERN = re.compile(
    r"\b(?:gpt|claude|gemini|llama|mistral|qwen|grok|deepseek|o[1-9])[- ]?\d"
)
VENDOR_SPECIFIC_PATHS = {
    ".claude",
    ".cursor",
    ".codex",
    ".agents",
    "appdata",
    "library/application support",
    "~/.config",
}
RANKING_CLAIMS = {
    "best model for",
    "best provider for",
    "top-ranked model",
    "top-ranked provider",
    "recommended model is",
    "recommended provider is",
    "ranking of models",
    "ranking of providers",
}


def _read_skill_text() -> str:
    assert SKILL_FILE.is_file(), f"missing canonical skill file: {SKILL_FILE}"
    return SKILL_FILE.read_text(encoding="utf-8")


def _reference_paths() -> list[Path]:
    assert REFERENCES_DIR.is_dir(), f"missing references directory: {REFERENCES_DIR}"
    return sorted(REFERENCES_DIR.glob("*.md"))


def _combined_text() -> str:
    parts = [_read_skill_text()]
    for path in _reference_paths():
        parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)


def _frontmatter() -> tuple[dict, str]:
    text = _read_skill_text()
    assert text.startswith("---"), "SKILL.md must open with YAML frontmatter"
    _, raw_frontmatter, body = text.split("---", 2)
    data = yaml.safe_load(raw_frontmatter)
    assert isinstance(data, dict), "frontmatter must parse to a mapping"
    return data, body


def test_skill_frontmatter_name_folder_and_keys_match() -> None:
    data, _ = _frontmatter()

    assert set(data) <= {"name", "description"}, f"unexpected frontmatter keys: {sorted(data)}"
    assert data["name"] == "inferencefit"
    assert SKILL_DIR.name == data["name"], "skill folder name must match the frontmatter name"


def test_skill_description_is_nonempty_and_bounded() -> None:
    data, _ = _frontmatter()
    description = data["description"]

    assert isinstance(description, str)
    assert description.strip(), "description must not be empty"
    assert len(description) <= 1024, "description must be at most 1024 characters"


def test_skill_description_states_capability_and_trigger_intents() -> None:
    data, _ = _frontmatter()
    description = data["description"].lower()

    assert "benchmark" in description, "description must state the capability it provides"
    triggers = [
        "model-selection",
        "model selection",
        "evaluate",
        "evaluation",
        "compare",
        "choose",
        "select",
    ]
    assert any(token in description for token in triggers), (
        "description must state the intents that should trigger the skill"
    )


def test_skill_body_stays_concise() -> None:
    text = _read_skill_text()
    assert len(text.splitlines()) < 500, "SKILL.md must stay below 500 lines"


def test_skill_has_exactly_three_expected_one_level_references() -> None:
    found = {path.name for path in _reference_paths()}
    assert found == EXPECTED_REFERENCE_FILES

    links = MARKDOWN_LINK.findall(_read_skill_text())
    reference_links = {link for link in links if "references/" in link}
    assert reference_links == EXPECTED_REFERENCE_LINKS

    for link in reference_links:
        assert (SKILL_DIR / link).is_file(), f"broken reference link: {link}"
        assert link.count("/") == 1, f"references must be one level deep: {link}"


def test_skill_references_do_not_link_to_nested_references() -> None:
    for path in _reference_paths():
        links = MARKDOWN_LINK.findall(path.read_text(encoding="utf-8"))
        for link in links:
            assert "references/" not in link, f"{path.name} links to a reference directory: {link}"
            target = link.rsplit("/", 1)[-1]
            assert target not in EXPECTED_REFERENCE_FILES, (
                f"{path.name} nests another reference file: {link}"
            )


def test_skill_names_workflow_stages() -> None:
    text = _combined_text().lower()
    for stage in [
        "preset",
        "representative",
        "validator",
        "credential",
        "repetition",
        "exploratory",
        "pareto",
        "cost",
    ]:
        assert stage in text, f"skill must cover workflow stage keyword: {stage}"


def test_skill_names_all_preset_ids() -> None:
    text = _combined_text()
    for preset_id in EXPECTED_PRESET_IDS:
        assert preset_id in text, f"skill must mention preset id: {preset_id}"


def test_skill_references_current_cli_commands() -> None:
    text = _combined_text()
    for invocation in [
        "inferencefit presets",
        "inferencefit init",
        "inferencefit validate",
        "inferencefit benchmark",
        "inferencefit skill path",
    ]:
        assert invocation in text, f"skill must reference CLI invocation: {invocation}"


def test_skill_documents_exploratory_envelope() -> None:
    text = _combined_text().lower()

    assert re.search(r"(?:\b3\b|three)[^\n]{0,60}candidates", text), "three-candidate bound"
    assert re.search(r"(?:\b5\b|five)[^\n]{0,60}cases", text), "five-case bound"
    assert re.search(r"(?:\b1\b|one|single)[^\n]{0,60}repetition", text), "one-repetition bound"


def test_skill_requires_representative_production_examples_warning() -> None:
    text = _combined_text().lower()
    assert "representative production" in text, "skill must require representative production cases"


def test_skill_prohibits_credential_values() -> None:
    text = _combined_text().lower()
    assert "credential" in text, "skill must address credentials"
    prohibition = re.search(
        r"(?:never|do not|does not|not\b)[^.\n]{0,80}"
        r"(?:print|expose|expos|reveal|serialize|serial|transmit|read aloud)",
        text,
    )
    assert prohibition, "skill must forbid exposing credential values"


def test_skill_covers_pareto_and_unknown_cost() -> None:
    text = _combined_text().lower()
    assert "pareto" in text, "skill must mention the Pareto frontier"
    assert re.search(r"unknown[^\n]{0,40}cost|cost[^\n]{0,40}unknown", text) or (
        "not zero cost" in text or "zero cost" in text
    ), "skill must warn that unknown cost is not zero cost"


def test_skill_distinguishes_exact_contains_from_semantic() -> None:
    text = _combined_text().lower()
    assert "semantic" in text
    assert "exact" in text
    assert "contains" in text


def test_skill_treats_local_python_validators_as_trusted_code() -> None:
    text = _combined_text().lower()
    assert "python" in text
    assert "validator" in text
    assert "trusted" in text


def test_skill_does_not_reference_nonexistent_commands() -> None:
    text = _combined_text()
    invoked = {
        token
        for token in CLI_INVOCATION.findall(text)
        if token not in NON_COMMAND_FOLLOWERS
    }
    unknown = invoked - KNOWN_CLI_SUBCOMMANDS
    assert not unknown, f"skill references nonexistent CLI commands: {sorted(unknown)}"

    assert {"presets", "init", "validate", "benchmark", "skill"} <= invoked


def test_skill_avoids_vendor_specific_skill_paths() -> None:
    text = _combined_text().lower()
    for marker in VENDOR_SPECIFIC_PATHS:
        assert marker not in text, f"skill must not hard-code vendor-specific path: {marker}"


def test_skill_avoids_provider_or_model_rankings() -> None:
    text = _combined_text()
    lowered = text.lower()

    for identifier in LIVE_MODEL_IDENTIFIERS:
        assert identifier not in text, f"skill must not name live models: {identifier}"
    assert not MODEL_NAME_PATTERN.search(lowered), "skill must not embed live model identifiers"

    for claim in RANKING_CLAIMS:
        assert claim not in lowered, f"skill must not make provider/model ranking claims: {claim}"


def test_skill_contains_no_secret_like_assignments() -> None:
    match = SECRET_ASSIGNMENT.search(_combined_text())
    assert match is None, f"skill contains a secret-like assignment: {match.group(0)}"


@pytest.mark.parametrize("path_name", sorted(EXPECTED_REFERENCE_FILES))
def test_expected_reference_files_exist_and_are_readable(path_name: str) -> None:
    path = REFERENCES_DIR / path_name
    assert path.is_file(), f"missing reference: {path}"
    assert path.read_text(encoding="utf-8").strip(), f"reference is empty: {path}"
