"""Shared constants and helpers for the public contracts."""

from __future__ import annotations

SCHEMA_VERSION = "0.1"
SUPPORTED_SCHEMA_VERSIONS: frozenset[str] = frozenset({SCHEMA_VERSION})


def validate_schema_version(value: str) -> str:
    """Return ``value`` when it is a supported schema version.

    Raises:
        ValueError: when the version is not supported by this build.
    """

    if value not in SUPPORTED_SCHEMA_VERSIONS:
        supported = ", ".join(sorted(SUPPORTED_SCHEMA_VERSIONS))
        raise ValueError(f"unsupported schema_version {value!r}; supported versions: {supported}")
    return value
