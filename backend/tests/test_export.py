import gzip
import json

import pytest
from fastapi.testclient import TestClient

from nova_backend import export
from nova_backend.api import app
from nova_backend.imports import import_report


def test_export_reads_full_paged_backend_and_preserves_rows(
    engine, tmp_path, fixtures, monkeypatch
):
    import_report(
        "grubhub",
        fixtures / "grubhub_menu_line_items.csv",
        True,
        True,
        engine=engine,
        raw_storage_path=tmp_path / "raw",
    )
    client = TestClient(app)

    def read(base, endpoint, params):
        # Force tiny pages to prove the exporter follows every cursor.
        response = client.get(f"/{endpoint}", params={**params, "limit": 2})
        assert response.status_code == 200
        return response.json()

    monkeypatch.setattr(export, "read_page", read)
    stores = [f"grubhub:{row['external_store_id']}" for row in export.collect("", "stores")]
    out = tmp_path / "export"
    manifest = export.export_dataset("http://localhost:8000", stores, out)
    assert manifest["totals"]["orders"] == 6
    assert manifest["totals"]["order_lines"] == 11
    with gzip.open(out / "order_lines.jsonl.gz", "rt") as stream:
        rows = [json.loads(line) for line in stream]
    assert len(rows) == 11
    assert all(row["source_details"]["raw_row"] for row in rows)
    assert all(row["is_synthetic"] for row in rows)
    with pytest.raises(FileExistsError):
        export.export_dataset("http://localhost:8000", stores, out)


def test_repeated_cursor_fails_without_infinite_loop(monkeypatch):
    monkeypatch.setattr(export, "read_page", lambda *args: {"data": [], "next_cursor": "same"})
    with pytest.raises(ValueError, match="Repeated"):
        export.collect("http://localhost:8000", "orders")


def test_export_does_not_accept_external_services(tmp_path):
    with pytest.raises(ValueError, match="local HTTP"):
        export.export_dataset("https://example.com", ["grubhub:1"], tmp_path / "out")
