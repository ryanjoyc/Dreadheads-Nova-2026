"""Boundary checks complementing the basic API integration coverage."""

import base64
import json
from datetime import datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from nova_backend import queries
from nova_backend.api import app
from nova_backend.db import get_session
from nova_backend.models import Order, OrderLine
from tests.test_imports import load


@pytest.fixture
def client(engine, tmp_path, fixtures):
    for source in ("doordash", "grubhub"):
        load(engine, tmp_path, fixtures, source)

    def session_override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client
    app.dependency_overrides.clear()


def test_item_pagination_and_latest_observed_label(client, engine):
    with Session(engine) as session, session.begin():
        line, order = session.execute(
            select(OrderLine, Order).join(Order, OrderLine.order_id == Order.id)
        ).first()
        item_id, store_id = line.external_item_id, str(order.source_store_id)
        order.placed_at_local = datetime(2026, 11, 7, 12, 0)
        line.item_name = "Latest observed label"
    complete = client.get("/items", params={"limit": 500}).json()["data"]
    expected = {(r["store_id"], r["external_item_id"]) for r in complete}
    assert len(expected) == len(complete)
    all_pages, cursor = [], None
    for _ in range(100):
        params = {"limit": 1}
        if cursor:
            params["cursor"] = cursor
        response = client.get("/items", params=params)
        assert response.status_code == 200, response.text
        page = response.json()
        all_pages.extend(page["data"])
        cursor = page["next_cursor"]
        if cursor is None:
            break
    else:
        pytest.fail("Item pagination did not terminate")
    assert len(all_pages) == len(expected)
    assert {(r["store_id"], r["external_item_id"]) for r in all_pages} == expected
    chosen = next(
        r for r in all_pages if r["store_id"] == store_id and r["external_item_id"] == item_id
    )
    assert chosen["item_name"] == "Latest observed label"
    assert chosen["last_seen_at_local"] == "2026-11-07T12:00:00"
    assert chosen["is_synthetic"] is True


def test_cursor_invalid_key_is_a_client_error(client):
    cursor = client.get("/items", params={"limit": 1}).json()["next_cursor"]
    payload = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
    payload["after"][0] = "not-a-uuid"
    invalid = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    response = client.get("/items", params={"cursor": invalid})
    assert response.status_code == 400


def test_deeply_nested_cursor_is_a_client_error(client):
    payload = "[" * 1000 + "0" + "]" * 1000
    invalid = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
    response = client.get("/orders", params={"cursor": invalid})
    assert response.status_code == 400


def test_unexpected_errors_do_not_leak_paths_or_credentials(client, monkeypatch):
    def broken_query(*_args):
        raise RuntimeError("postgresql://private:password@db /private/raw.csv")

    monkeypatch.setattr(queries, "list_orders", broken_query)
    response = client.get("/orders")
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}


def test_fractional_quantity_keeps_precision(client, engine):
    with Session(engine) as session, session.begin():
        line = session.scalar(select(OrderLine))
        line.quantity = Decimal("1.123456")
        line_id = str(line.id)
    rows = client.get("/order-lines", params={"limit": 500}).json()["data"]
    chosen = next(row for row in rows if row["id"] == line_id)
    assert chosen["quantity"] == "1.123456"
    assert all(isinstance(row["quantity"], int) for row in rows if row["id"] != line_id)
