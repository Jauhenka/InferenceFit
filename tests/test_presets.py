"""Focused tests for the built-in workload preset registry."""

from __future__ import annotations

import dataclasses

import pytest

from inferencefit.presets import (
    PresetDefinition,
    UnknownPresetError,
    get_preset,
    list_presets,
)


def test_registry_has_exact_stable_presets() -> None:
    assert [preset.identifier for preset in list_presets()] == [
        "coding",
        "document-processing",
        "structured-extraction",
    ]


def test_registry_descriptions_match_design_cli_strings() -> None:
    assert {preset.identifier: preset.description for preset in list_presets()} == {
        "coding": "Code generation and transformation with deterministic checks.",
        "document-processing": (
            "Document classification and adaptable document-quality evaluation."
        ),
        "structured-extraction": "Schema-checked JSON extraction with exact expected fields.",
    }


def test_registry_metadata_is_unique_and_complete() -> None:
    presets = list_presets()
    assert all(preset.description.strip() and preset.template_name for preset in presets)
    assert len({preset.identifier for preset in presets}) == len(presets)


def test_list_presets_returns_immutable_tuple() -> None:
    assert isinstance(list_presets(), tuple)


def test_preset_definition_is_frozen() -> None:
    preset = get_preset("coding")
    assert isinstance(preset, PresetDefinition)
    with pytest.raises(dataclasses.FrozenInstanceError):
        preset.identifier = "renamed"  # type: ignore[misc]


def test_lookup_returns_registered_definition() -> None:
    preset = get_preset("structured-extraction")
    assert preset.identifier == "structured-extraction"
    assert preset.template_name == "structured-extraction"


def test_unknown_preset_fails_cleanly() -> None:
    with pytest.raises(UnknownPresetError, match="unknown preset 'missing'"):
        get_preset("missing")
