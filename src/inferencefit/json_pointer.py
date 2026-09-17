"""RFC 6901 JSON Pointer resolution.

Pointers are resolved against JSON-compatible Python documents (mappings,
sequences, and scalars). Resolution is strict: unusable pointers raise
:class:`~inferencefit.errors.JsonPointerError` rather than returning a sentinel.
"""

from __future__ import annotations

from typing import Any

from inferencefit.errors import JsonPointerError


def _unescape(token: str) -> str:
    """Return the decoded reference token for ``token``.

    ``~1`` decodes to ``/`` and ``~0`` decodes to ``~``. Any other ``~`` escape
    is invalid per RFC 6901.
    """

    if "~" not in token:
        return token
    result: list[str] = []
    index = 0
    length = len(token)
    while index < length:
        char = token[index]
        if char != "~":
            result.append(char)
            index += 1
            continue
        if index + 1 >= length:
            raise JsonPointerError(f"invalid escape sequence in token {token!r}")
        following = token[index + 1]
        if following == "0":
            result.append("~")
        elif following == "1":
            result.append("/")
        else:
            raise JsonPointerError(f"invalid escape sequence '~{following}' in token {token!r}")
        index += 2
    return "".join(result)


def _tokens(pointer: str) -> list[str]:
    if pointer == "":
        return []
    if not pointer.startswith("/"):
        raise JsonPointerError(f"JSON pointer must be empty or start with '/': {pointer!r}")
    return [_unescape(token) for token in pointer[1:].split("/")]


def _array_index(token: str) -> int:
    if not token.isdigit() or (len(token) > 1 and token[0] == "0"):
        raise JsonPointerError(f"invalid array index token {token!r} in JSON pointer")
    return int(token)


def _resolve_token(document: Any, token: str) -> Any:
    if isinstance(document, dict):
        if token not in document:
            raise JsonPointerError(f"missing key {token!r} in JSON pointer")
        return document[token]
    if isinstance(document, list):
        index = _array_index(token)
        if index >= len(document):
            raise JsonPointerError(f"array index {index} is out of range for JSON pointer")
        return document[index]
    raise JsonPointerError(
        f"cannot descend into scalar while resolving JSON pointer token {token!r}"
    )


def resolve_pointer(document: Any, pointer: str) -> Any:
    """Resolve ``pointer`` against ``document`` and return the referenced value.

    Args:
        document: A JSON-compatible Python object.
        pointer: An RFC 6901 JSON Pointer; ``""`` refers to ``document``.

    Raises:
        JsonPointerError: when the pointer is malformed or does not resolve.
    """

    current = document
    for token in _tokens(pointer):
        current = _resolve_token(current, token)
    return current
