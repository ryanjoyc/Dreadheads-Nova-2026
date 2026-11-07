import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from nova_backend.api import app
from nova_backend.db import get_session
from tests.test_imports import load


@pytest.fixture
def client(engine, tmp_path, fixtures):
    for source in ["doordash", "grubhub"]:
        load(engine, tmp_path, fixtures, source)

    def session_override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client
    app.dependency_overrides.clear()


def collect(client, endpoint, params=None):
    query = {"limit": 2, **(params or {})}
    rows = []
    for _ in range(100):
        response = client.get(endpoint, params=query)
        assert response.status_code == 200, response.text
        page = response.json()
        assert set(page) == {"data", "next_cursor"}
        rows.extend(page["data"])
        if page["next_cursor"] is None:
            break
        query["cursor"] = page["next_cursor"]
    else:
        pytest.fail("Pagination did not terminate")
    assert len({json.dumps(r, sort_keys=True) for r in rows}) == len(rows)
    return rows


@pytest.mark.parametrize(
    "endpoint,count", [("/stores", 4), ("/orders", 12), ("/order-lines", 21), ("/imports", 2)]
)
def test_collections_and_pagination(client, endpoint, count):
    assert len(collect(client, endpoint)) == count


def test_items_are_store_scoped_observed_identities(client):
    stores = collect(client, "/stores")
    items = collect(client, "/items")
    assert items
    for store in stores:
        store_id = store.get("id", store.get("store_id"))
        subset = collect(client, "/items", {"store_id": store_id})
        assert subset
        assert all(row["store_id"] == store_id for row in subset)


def test_source_store_date_filters(client):
    dd = collect(client, "/orders", {"source": "doordash"})
    assert len(dd) == 6 and all(row["source"] == "doordash" for row in dd)
    store_id = dd[0]["store_id"]
    scoped = collect(client, "/order-lines", {"store_id": store_id})
    assert scoped and all(row["store_id"] == store_id for row in scoped)
    day = dd[0]["placed_at_local"][:10]
    included = collect(client, "/orders", {"date_start": day, "date_end": "2026-05-02"})
    assert included and all(r["placed_at_local"].startswith(day) for r in included)
    assert collect(client, "/orders", {"date_end": day}) == []
    assert collect(client, "/orders", {"store_id": str(uuid4())}) == []


def test_decimal_null_and_provenance_contract(client):
    lines = collect(client, "/order-lines")
    assert all(isinstance(row["unit_price"], str) for row in lines)
    assert all(row["is_synthetic"] and row["last_import_run_id"] for row in lines)
    assert all(row["modifiers"] is None for row in lines if row["source"] == "doordash")
    gh = collect(client, "/orders", {"source": "grubhub"})
    assert all(row["subtotal"] is None for row in gh)
    imports = collect(client, "/imports", {"status": "succeeded"})
    assert len(imports) == 2
    assert all("raw_file_reference" not in row for row in imports)
    assert all(row["is_synthetic"] for row in imports)


@pytest.mark.parametrize(
    "endpoint,params",
    [
        ("/orders", {"source": "other"}),
        ("/orders", {"date_start": "not-a-date"}),
        ("/orders", {"date_start": "2026-05-02", "date_end": "2026-05-01"}),
        ("/orders", {"store_id": "not-a-uuid"}),
        ("/orders", {"limit": 0}),
        ("/orders", {"limit": 501}),
        ("/orders", {"cursor": "invalid"}),
        ("/imports", {"status": "invalid"}),
    ],
)
def test_invalid_filters_return_400(client, endpoint, params):
    response = client.get(endpoint, params=params)
    assert response.status_code == 400, response.text


def test_cursor_cannot_cross_endpoint_or_filters(client):
    cursor = client.get("/orders", params={"limit": 1}).json()["next_cursor"]
    assert cursor
    assert client.get("/order-lines", params={"cursor": cursor}).status_code == 400
    assert client.get("/orders", params={"cursor": cursor, "source": "doordash"}).status_code == 400


def test_documentation_and_openapi(client):
    assert client.get("/docs").status_code == 200
    schema = client.get("/openapi.json").json()
    assert set(schema["paths"]) == {
        "/stores",
        "/orders",
        "/orders/filter",
        "/order-lines",
        "/items",
        "/imports",
        "/dishes/top",
        "/rush-hours",
    }
