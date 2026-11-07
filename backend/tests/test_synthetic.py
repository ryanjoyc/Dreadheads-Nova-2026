import csv
import hashlib
from decimal import Decimal

import pytest

from nova_backend.parsing import parse_report
from nova_backend.synthetic import DD_HEADERS, GH_HEADERS, generate


def test_synthetic_reports_are_deterministic_and_parser_compatible(tmp_path, fixtures):
    first = generate(tmp_path / "one", orders=512)
    second = generate(tmp_path / "two", orders=512)
    assert first == second
    total_orders = total_lines = 0
    for source, entry in first["sources"].items():
        path = tmp_path / "one" / entry["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]
        report = parse_report(source, path)
        assert len(report.orders) == entry["orders"]
        assert report.row_count == entry["lines"]
        assert (
            sum(line.quantity for o in report.orders.values() for line in o.lines)
            == entry["quantity"]
        )
        total_orders += len(report.orders)
        total_lines += report.row_count
        filename = (
            "doordash_order_detail.csv" if source == "doordash" else "grubhub_menu_line_items.csv"
        )
        with (fixtures / filename).open(newline="") as stream:
            assert next(csv.reader(stream)) == entry["columns"]
    assert total_orders == 512
    assert total_lines > total_orders
    assert first["is_synthetic"] is True


def test_generated_dd_order_totals_and_line_identities(tmp_path):
    manifest = generate(tmp_path / "demo", orders=512)
    report = parse_report("doordash", tmp_path / "demo" / manifest["sources"]["doordash"]["path"])
    repeated = False
    for order in report.orders.values():
        assert order.subtotal == sum(line.unit_price * line.quantity for line in order.lines)
        assert len({line.external_line_id for line in order.lines}) == len(order.lines)
        if len({line.external_item_id for line in order.lines}) < len(order.lines):
            repeated = True
        assert all(line.external_item_id.startswith("00") for line in order.lines)
        assert all(line.quantity > Decimal(0) for line in order.lines)
    assert repeated


def test_synthetic_refuses_overwrite_and_invalid_count(tmp_path):
    output = tmp_path / "demo"
    generate(output, orders=4)
    original = (output / "manifest.json").read_bytes()
    with pytest.raises(ValueError, match="empty"):
        generate(output, orders=4)
    assert (output / "manifest.json").read_bytes() == original
    with pytest.raises(ValueError, match="positive"):
        generate(tmp_path / "bad", orders=0)


def test_exact_report_headers():
    assert len(DD_HEADERS) == 23
    assert len(GH_HEADERS) == 17
