import base64
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from nova_backend.api import app
from nova_backend.pagination import InvalidCursor, decode_cursor, encode_cursor


@pytest.mark.parametrize("item_key", ["\u0000", "\ud800"])
def test_postgresql_incompatible_cursor_text_is_rejected(item_key):
    cursor = encode_cursor("items", {}, [str(uuid4()), item_key])
    with pytest.raises(InvalidCursor):
        decode_cursor(cursor, "items", {}, key_count=2)


def test_excessively_nested_json_cursor_is_rejected():
    raw = ("[" * 1100 + "0" + "]" * 1100).encode()
    cursor = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    with pytest.raises(InvalidCursor):
        decode_cursor(cursor, "items", {}, key_count=2)


@pytest.mark.parametrize("item_key", ["\u0000", "\ud800"])
def test_bad_cursor_text_is_http_400(item_key):
    cursor = encode_cursor("items", {"source": None, "store_id": None}, [str(uuid4()), item_key])
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/items", params={"cursor": cursor})
    assert response.status_code == 400
