"""Errors raised while loading or validating InferenceFit contracts."""

from __future__ import annotations


class InferenceFitError(Exception):
    """Base class for all InferenceFit errors."""


class ContractError(InferenceFitError, ValueError):
    """A public contract was malformed or violated a rule."""


class SchemaVersionError(ContractError):
    """An unsupported ``schema_version`` was supplied."""


class SpecLoadError(ContractError):
    """An evaluation spec could not be parsed from a document."""


class DatasetError(InferenceFitError, ValueError):
    """A dataset document was malformed."""


class JsonPointerError(InferenceFitError, ValueError):
    """A JSON Pointer could not be resolved."""


class ValidatorError(InferenceFitError):
    """A validator could not be constructed or run."""


class CredentialError(InferenceFitError):
    """A credential reference could not be resolved."""


class MissingCredentialError(CredentialError):
    """No environment variable provided the requested secret."""
