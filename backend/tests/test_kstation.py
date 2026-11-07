import csv
import hashlib
from collections import Counter
from datetime import date
from decimal import Decimal

import pytest

from nova_backend.kstation import DAY_TYPES, MENU, STORE_IDS, generate, hourly_profile
from nova_backend.parsing import parse_report
from nova_backend.synthetic import DD_HEADERS, GH_HEADERS


@pytest.fixture(scope="module")
def scenario(tmp_path_factory):
    path = tmp_path_factory.mktemp("kstation") / "dataset"
    return path, generate(path)


def test_kstation_deterministic_source_files(scenario, tmp_path):
    path, manifest = scenario
    repeated = generate(tmp_path / "repeat")
    assert repeated == manifest
    for source, entry in manifest["sources"].items():
        assert hashlib.sha256((path / entry["path"]).read_bytes()).hexdigest() == entry["sha256"]
        assert (path / entry["path"]).read_bytes() == (
            tmp_path / "repeat" / entry["path"]
        ).read_bytes()


def test_kstation_actual_orders_and_time_windows(scenario):
    path, manifest = scenario
    observed_hours, observed_quarters, observed_dates = Counter(), Counter(), Counter()
    total_lines, total_orders = 0, 0
    saw_repeated_dish = False
    blank_pos = False
    for source, entry in manifest["sources"].items():
        parsed = parse_report(source, path / entry["path"])
        assert set(parsed.stores) == {STORE_IDS[source]}
        assert len(parsed.orders) == entry["orders"]
        assert parsed.row_count == entry["lines"]
        total_lines += parsed.row_count
        total_orders += len(parsed.orders)
        assert (
            sum(line.quantity for order in parsed.orders.values() for line in order.lines)
            == entry["quantity"]
        )
        for order in parsed.orders.values():
            placed = order.placed_at_local
            minute = placed.hour * 60 + placed.minute
            assert 11 * 60 <= minute < 16 * 60 or 17 * 60 <= minute < 20 * 60 + 30
            assert placed.year == 2026 and placed.month == 10
            day = placed.date().isoformat()
            observed_dates[day] += 1
            observed_hours[(day, placed.hour)] += 1
            observed_quarters[(day, f"{placed.hour:02d}:{placed.minute // 15 * 15:02d}")] += 1
            saw_repeated_dish |= len({line.external_item_id for line in order.lines}) < len(
                order.lines
            )
            blank_pos |= any(
                line.source_details["raw_row"].get(
                    "external_order_id" if source == "doordash" else "partner_order_id"
                )
                == ""
                for line in order.lines
            )
            if source == "doordash":
                assert order.subtotal == sum(
                    line.unit_price * line.quantity for line in order.lines
                )
                assert len({line.external_line_id for line in order.lines}) == len(order.lines)
                assert all(line.modifiers is None for line in order.lines)
        with (path / entry["path"]).open(newline="") as stream:
            assert next(csv.reader(stream)) == (DD_HEADERS if source == "doordash" else GH_HEADERS)
    assert total_orders == manifest["orders"]
    assert 16000 <= total_orders <= 21000
    assert total_lines > total_orders
    assert saw_repeated_dish and blank_pos
    assert len(observed_dates) == 31
    for row in manifest["daily"]:
        ds = row["date"]
        assert observed_dates[ds] == row["target_orders"]
        bounds = DAY_TYPES[row["day_type"]]
        assert bounds["orders"][0] <= observed_dates[ds] <= bounds["orders"][1]
        actual_peak = max(n for (day, _), n in observed_hours.items() if day == ds)
        assert bounds["peak"][0] <= actual_peak <= bounds["peak"][1]
        assert actual_peak == row["target_peak_hour_orders"]
        for hour, count in row["hourly_orders"].items():
            assert observed_hours[(ds, int(hour))] == count
        assert sum(row["quarter_hour_orders"].values()) == row["target_orders"]
        for quarter, count in row["quarter_hour_orders"].items():
            assert observed_quarters[(ds, quarter)] == count
        if date.fromisoformat(ds).weekday() == 3:
            assert 95 <= observed_hours[(ds, 14)] <= 110
        else:
            assert observed_hours[(ds, 14)] <= 65
        if ds == "2026-10-21":
            assert 100 <= observed_hours[(ds, 15)] <= 110
        else:
            assert observed_hours[(ds, 15)] <= 45


@pytest.mark.parametrize("seed", [0, 1, 7, 42, 20261107])
def test_hour_constraints_hold_across_seeds(seed):
    import random

    rng = random.Random(seed)
    for n in range(1, 32):
        kind, total, peak, hours = hourly_profile(rng, date(2026, 10, n))
        assert sum(hours.values()) == total
        assert max(hours.values()) == peak
        assert DAY_TYPES[kind]["orders"][0] <= total <= DAY_TYPES[kind]["orders"][1]
        assert DAY_TYPES[kind]["peak"][0] <= peak <= DAY_TYPES[kind]["peak"][1]


def test_kstation_price_mapping_and_overwrite_protection(scenario):
    path, manifest = scenario
    assert len(MENU) == 19
    assert {m["grubhub_item_id"] for m in manifest["menu"]} == {m[0] for m in MENU}
    assert all(
        Decimal(m["lunch_price_usd"]) <= Decimal(m["dinner_price_usd"]) for m in manifest["menu"]
    )
    old_hash = hashlib.sha256((path / "manifest.json").read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="empty"):
        generate(path)
    assert hashlib.sha256((path / "manifest.json").read_bytes()).hexdigest() == old_hash
