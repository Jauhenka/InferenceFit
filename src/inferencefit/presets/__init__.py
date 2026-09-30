"""Built-in workload preset registry.

The registry is a fixed, immutable tuple of :class:`PresetDefinition` records.
Identifiers and descriptions are stable public values; they intentionally match
the ``inferencefit presets`` CLI output. There is no registration or plugin
mechanism.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "PresetDefinition",
    "UnknownPresetError",
    "get_preset",
    "list_presets",
]


class UnknownPresetError(LookupError):
    """Raised when a requested preset identifier is not registered."""


@dataclass(frozen=True)
class PresetDefinition:
    """A single built-in workload preset."""

    identifier: str
    description: str
    template_name: str


_PRESETS: tuple[PresetDefinition, ...] = (
    PresetDefinition(
        identifier="coding",
        description="Code generation and transformation with deterministic checks.",
        template_name="coding",
    ),
    PresetDefinition(
        identifier="document-processing",
        description="Document classification and adaptable document-quality evaluation.",
        template_name="document-processing",
    ),
    PresetDefinition(
        identifier="structured-extraction",
        description="Schema-checked JSON extraction with exact expected fields.",
        template_name="structured-extraction",
    ),
)

_BY_IDENTIFIER: dict[str, PresetDefinition] = {preset.identifier: preset for preset in _PRESETS}


def list_presets() -> tuple[PresetDefinition, ...]:
    """Return the built-in presets in stable registry order."""

    return _PRESETS


def get_preset(identifier: str) -> PresetDefinition:
    """Return the registered preset for ``identifier``.

    Raises :class:`UnknownPresetError` when ``identifier`` is not registered.
    """

    try:
        return _BY_IDENTIFIER[identifier]
    except KeyError:
        raise UnknownPresetError(f"unknown preset '{identifier}'") from None
