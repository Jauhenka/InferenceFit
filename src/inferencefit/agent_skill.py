"""Discovery of the packaged, portable InferenceFit Agent Skill.

The canonical skill lives as static package resources alongside the source
tree (``src/inferencefit/skills/inferencefit``). This module exposes only the
path to those resources; it does not copy, link, or install them.
"""

from __future__ import annotations

from pathlib import Path

SKILL_DIRECTORY_NAME = "inferencefit"
SKILL_FILE_NAME = "SKILL.md"
REQUIRED_REFERENCE_NAMES: tuple[str, ...] = (
    "presets.md",
    "validators.md",
    "interpreting-results.md",
)


def canonical_skill_path() -> Path:
    """Return the absolute path to the packaged canonical Agent Skill.

    Raises:
        RuntimeError: If the skill directory, its ``SKILL.md``, or any of the
            expected one-level reference files are missing.
    """

    skill_root = (Path(__file__).parent / "skills" / SKILL_DIRECTORY_NAME).resolve()

    if not skill_root.is_dir():
        raise RuntimeError(
            f"Agent Skill directory is missing: {skill_root}. "
            "The packaged InferenceFit skill resources were not found."
        )

    skill_file = skill_root / SKILL_FILE_NAME
    if not skill_file.is_file():
        raise RuntimeError(
            f"Agent Skill entrypoint is missing: {skill_file}. "
            "The packaged SKILL.md was not found."
        )

    references = skill_root / "references"
    missing = [
        name for name in REQUIRED_REFERENCE_NAMES if not (references / name).is_file()
    ]
    if missing:
        raise RuntimeError(
            "Agent Skill references are missing: "
            + ", ".join(str(references / name) for name in missing)
            + ". The packaged skill is incomplete."
        )

    return skill_root
