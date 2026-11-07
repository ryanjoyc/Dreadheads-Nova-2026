"""Opaque keyset cursors scoped to an endpoint and its active filters."""

import base64
import binascii
import hashlib
import json
from typing import Any


class InvalidCursor(ValueError):
    """The client cursor is malformed or belongs to a different query."""


def _filter_digest(filters: dict[str, Any]) -> str:
    encoded = json.dumps(filters, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode()).hexdigest()


def encode_cursor(scope: str, filters: dict[str, Any], after: list[str]) -> str:
    payload = {"v": 1, "scope": scope, "filters": _filter_digest(filters), "after": after}
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(
    cursor: str | None, scope: str, filters: dict[str, Any], key_count: int = 1
) -> list[str] | None:
    if cursor is None:
        return None
    try:
        if len(cursor) > 4096 or not cursor or "=" in cursor:
            raise ValueError
        raw = base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True)
        payload = json.loads(raw)
        if (
            not isinstance(payload, dict)
            or set(payload) != {"v", "scope", "filters", "after"}
            or payload["v"] != 1
            or payload["scope"] != scope
            or payload["filters"] != _filter_digest(filters)
            or not isinstance(payload["after"], list)
            or len(payload["after"]) != key_count
            or not all(isinstance(key, str) and key for key in payload["after"])
        ):
            raise ValueError
        for key in payload["after"]:
            if "\x00" in key:
                raise ValueError
            key.encode("utf-8")
        return payload["after"]
    except (ValueError, TypeError, KeyError, UnicodeError, binascii.Error, RecursionError) as exc:
        raise InvalidCursor("Invalid cursor for this endpoint and filter set") from exc
