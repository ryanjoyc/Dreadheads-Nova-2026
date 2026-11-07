"""Exercise the independent artifact verifier without a database or generator."""

import csv
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "analyze_sales_demo", Path(__file__).resolve().parents[1] / "scripts/analyze_sales_demo.py"
)
analysis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)


def write_export(root, collections):
    exported = root / "backend_export"
    exported.mkdir(exist_ok=True)
    files = {}
    for name, rows in collections.items():
        path = exported / f"{name}.jsonl.gz"
        with gzip.open(path, "wt") as stream:
            for row in rows:
                stream.write(json.dumps(row) + "\n")
        files[path.name] = {
            "rows": len(rows),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    manifest = {
        "is_synthetic": True,
        "files": files,
        "totals": {"orders": 4, "order_lines": 4, "quantity": "4"},
    }
    (exported / "export_manifest.json").write_text(json.dumps(manifest))


def fixture(root):
    reports = root / "platform_reports"
    reports.mkdir()
    collections = {name: [] for name in analysis.COLLECTIONS}
    for source, fields in analysis.REPORTS.items():
        filename, store_key, order_key, qty_key, item_key, price_key, day_key, time_key = fields
        raw_rows = []
        for n in (1, 2):
            external_store = f"{source}-00{n}"
            raw = {
                store_key: external_store,
                order_key: f"000{n}",
                qty_key: "1",
                item_key: "item-01",
                price_key: "9.50",
                day_key: "2026-05-01",
                time_key: "12:00:00",
                "subtotal": "9.50",
                "order_number": f"000{n}",
                "order_item_id": f"line-00{n}",
                "menu_item_modifiers": "[]",
            }
            raw_rows.append(raw)
            store = {
                "id": external_store,
                "source": source,
                "external_store_id": external_store,
                "store_name": "Synthetic cafe",
            }
            order = {
                "id": f"order-{external_store}",
                "source": source,
                "store_id": store["id"],
                "external_store_id": external_store,
                "external_order_id": raw[order_key],
                "order_number": raw["order_number"],
                "placed_at_local": "2026-05-01T12:00:00",
                "fulfillment": "delivery",
                "subtotal": "9.50" if source == "doordash" else None,
                "last_import_run_id": source,
                "is_synthetic": True,
            }
            line = {
                **order,
                "id": f"line-{external_store}",
                "order_id": order["id"],
                "external_item_id": "item-01",
                "item_name": "Synthetic bowl",
                "external_line_id": raw["order_item_id"] if source == "doordash" else None,
                "quantity": 1,
                "unit_price": "9.50",
                "modifiers": None if source == "doordash" else [],
                "source_details": {"raw_row": raw},
            }
            item = {
                "source": source,
                "external_store_id": external_store,
                "external_item_id": "item-01",
                "is_synthetic": True,
            }
            collections["stores"].append(store)
            collections["orders"].append(order)
            collections["order_lines"].append(line)
            collections["items"].append(item)
        collections["imports"].append({"id": source, "is_synthetic": True, "status": "succeeded"})
        with (reports / filename).open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(raw_rows[0]))
            writer.writeheader()
            writer.writerows(raw_rows)
    # Full calendar range gives a meaningful weekday denominator even with sparse sales.
    for rows in (collections["orders"], collections["order_lines"]):
        rows[-1]["placed_at_local"] = "2026-05-08T12:00:00"
    collections["order_lines"][-1]["source_details"]["raw_row"]["order_date"] = "2026-05-08"
    path = reports / analysis.REPORTS["grubhub"][0]
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream)
        headers, rows = reader.fieldnames, list(reader)
    rows[-1]["order_date"] = "2026-05-08"
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)
    write_export(root, collections)
    return collections


def test_analysis_reconciles_and_uses_calendar_day_denominators(tmp_path):
    fixture(tmp_path)
    report = analysis.analyze(tmp_path)
    assert report["totals"] == {"stores": 4, "orders": 4, "order_lines": 4, "quantity": "4"}
    friday = next(row for row in report["weekday_demand"] if row["weekday"] == "Friday")
    assert friday["calendar_days"] == 2
    assert friday["orders_per_day"] == 2
    assert "verified example analysis" in analysis.render(report)


def test_analysis_rejects_changed_quantity_even_with_updated_export_hash(tmp_path):
    collections = fixture(tmp_path)
    collections["order_lines"][0]["quantity"] = 2
    write_export(tmp_path, collections)
    with pytest.raises(ValueError, match="quantity changed"):
        analysis.analyze(tmp_path)


def test_analysis_rejects_extra_original_row_field(tmp_path):
    collections = fixture(tmp_path)
    collections["order_lines"][0]["source_details"]["raw_row"]["invented"] = "not from CSV"
    write_export(tmp_path, collections)
    with pytest.raises(ValueError, match="Original CSV rows differ"):
        analysis.analyze(tmp_path)


def test_reconciliation_accepts_one_store_per_platform(tmp_path):
    collections = fixture(tmp_path)
    for name in ("stores", "orders", "order_lines", "items"):
        key = "external_store_id" if name in {"stores", "items"} else "store_id"
        collections[name] = [row for row in collections[name] if row[key].endswith("001")]
    for _, fields in analysis.REPORTS.items():
        path = tmp_path / "platform_reports" / fields[0]
        with path.open(newline="") as stream:
            reader = csv.DictReader(stream)
            headers, rows = reader.fieldnames, list(reader)
        with path.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=headers)
            writer.writeheader()
            writer.writerows(row for row in rows if row[fields[1]].endswith("001"))
    write_export(tmp_path, collections)
    manifest_path = tmp_path / "backend_export/export_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["totals"] = {"orders": 2, "order_lines": 2, "quantity": "2"}
    manifest_path.write_text(json.dumps(manifest))
    report = analysis.analyze(tmp_path, expected_store_count=2)
    assert report["totals"]["stores"] == report["totals"]["orders"] == 2
