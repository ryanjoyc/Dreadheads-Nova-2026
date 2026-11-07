"""Order search and dish ranking over the twelve seeded fixture orders (all on 2026-05-01)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from nova_backend.api import app
from nova_backend.db import get_session
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


def search(client, **params):
    query = {"limit": 2, **params}
    rows = []
    for _ in range(100):
        response = client.get("/orders/filter", params=query)
        assert response.status_code == 200, response.text
        page = response.json()
        rows.extend(page["data"])
        if page["next_cursor"] is None:
            return rows
        query["cursor"] = page["next_cursor"]
    pytest.fail("Pagination did not terminate")


def test_filter_pages_all_orders_oldest_first_with_items(client):
    rows = search(client)
    assert len(rows) == 12
    assert len({row["id"] for row in rows}) == 12
    times = [row["placed_at_local"] for row in rows]
    assert times == sorted(times)
    assert sum(len(row["items"]) for row in rows) == 21
    basket = next(row for row in rows if row["external_order_id"] == "009896B6")
    assert {item["item_name"] for item in basket["items"]} == {
        "Chicken Tender Basket",
        "Chicken Burrito",
        "Double Smash Burger",
    }


def test_filter_by_meal_name_is_case_insensitive_substring(client):
    rows = search(client, item_name="smash burger")
    assert {row["external_order_id"] for row in rows} == {
        "009896B6",
        "50000077",
        "50198956",
        "50198983",
    }
    assert search(client, item_name="100%_") == []


def test_filter_by_store_date_and_time_of_day(client):
    strip = search(client, store_name="strip")
    assert len(strip) == 6
    assert all(row["store_name"] == "Steel City Bowls - Strip District" for row in strip)
    assert len(search(client, date="2026-05-01")) == 12
    assert search(client, date="2026-05-02") == []
    window = search(client, time_start="11:00", time_end="11:15")
    assert len(window) == 5
    assert all("11:00:00" <= row["placed_at_local"][11:] < "11:15:00" for row in window)
    overnight = search(client, time_start="23:00", time_end="11:00")
    assert [row["external_order_id"] for row in overnight] == ["00989694"]
    combined = search(
        client, store_name="craig", item_name="burger", date="2026-05-01", time_end="11:30"
    )
    assert [row["external_order_id"] for row in combined] == ["009896B6"]


@pytest.mark.parametrize(
    "params",
    [
        {"date": "2026-05-01", "date_start": "2026-05-01"},
        {"date_start": "2026-05-02", "date_end": "2026-05-01"},
        {"time_start": "11:00", "time_end": "11:00"},
        {"time_start": "25:00"},
        {"item_name": ""},
    ],
)
def test_filter_rejects_invalid_input(client, params):
    assert client.get("/orders/filter", params=params).status_code == 400


def test_filter_cursor_is_bound_to_its_filters(client):
    cursor = client.get("/orders/filter", params={"limit": 1}).json()["next_cursor"]
    response = client.get("/orders/filter", params={"limit": 1, "cursor": cursor, "item_name": "x"})
    assert response.status_code == 400


def test_top_dishes_ranks_by_units_then_orders(client):
    response = client.get("/dishes/top", params={"limit": 3, "date": "2026-05-01"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["date_start"] == "2026-05-01" and body["date_end"] == "2026-05-02"
    assert [(d["rank"], d["item_name"], d["units"], d["orders"]) for d in body["data"]] == [
        (1, "Fountain Drink", 4, 2),
        (2, "Chicken Tender Basket", 3, 3),
        (3, "Smash Burger", 3, 3),
    ]


def test_top_dishes_scopes_and_limits(client):
    assert len(client.get("/dishes/top").json()["data"]) == 10
    assert len(client.get("/dishes/top", params={"limit": 100}).json()["data"]) == 13
    craig = client.get("/dishes/top", params={"limit": 1, "store_name": "Craig"}).json()
    assert craig["data"][0]["item_name"] == "Double Smash Burger"
    assert craig["data"][0]["units"] == 2
    empty = client.get("/dishes/top", params={"date_start": "2026-06-01"}).json()
    assert empty["data"] == []
    for limit in (0, 101):
        assert client.get("/dishes/top", params={"limit": limit}).status_code == 400
