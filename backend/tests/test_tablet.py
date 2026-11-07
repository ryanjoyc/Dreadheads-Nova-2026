"""Pure sales forecast checks; run with --noconftest (no database required)."""

from datetime import date, datetime

import pytest

from nova_backend.tablet import analyze_lines, analyze_outlook


def line(identity, order, day, *, source="doordash", quantity=1, hour=12, store=None):
    return {
        "id": identity,
        "order_id": order,
        "source": source,
        "external_store_id": store or {"doordash": "9900201", "grubhub": "8800201"}[source],
        "external_item_id": "0099020001" if source == "doordash" else "KS-M01",
        "placed_at_local": datetime.fromisoformat(f"{day}T{hour:02d}:00:00"),
        "quantity": quantity,
        "is_synthetic": True,
    }


def test_forecast_excludes_target_and_future_counts_orders_once():
    rows = [
        line("a", "order1", "2026-10-01", quantity=2),
        line("b", "order1", "2026-10-01", quantity=3),
        line("c", "order2", "2026-10-08", quantity=3),
        line("d", "observed", "2026-10-15", quantity=99),
        line("e", "future", "2026-10-22", quantity=999),
    ]
    result = analyze_lines(rows, date(2026, 10, 15))
    assert result["history_dates"] == ["2026-10-01", "2026-10-08"]
    assert result["forecast"]["orders"] == 1
    assert result["forecast"]["dishes"][0]["quantity"] == 4
    assert result["observed"]["dishes"][0]["quantity"] == 99
    assert len(result["forecast"]["slots"]) == 96
    assert result["forecast"]["slots"][0]["expected_orders"] == 0


def test_explicit_cohort_and_source_filter_and_menu_mapping():
    rows = [
        line("a", "dd", "2026-10-01", quantity=2),
        line("b", "gh", "2026-10-01", source="grubhub", quantity=3),
        line("c", "other", "2026-10-01", store="9900101", quantity=1000),
    ]
    both = analyze_lines(rows, date(2026, 10, 8))
    assert both["forecast"]["orders"] == 2
    assert len(both["forecast"]["dishes"]) == 1
    assert both["forecast"]["dishes"][0]["quantity"] == 5
    gh = analyze_lines(rows, date(2026, 10, 8), "grubhub")
    assert gh["forecast"]["orders"] == 1
    assert gh["forecast"]["dishes"][0]["quantity"] == 3


def test_no_history_is_explicit_and_zeroes_do_not_become_rushes():
    result = analyze_lines([line("a", "target", "2026-10-01")], date(2026, 10, 1))
    assert result["history_days"] == 0
    assert result["forecast"]["rushes"] == []
    assert result["forecast"]["dishes"] == []
    assert result["forecast"]["peak_at"] is None


def test_rush_window_and_projected_dishes_use_earlier_days():
    rows = [line(str(i), str(i), "2026-10-01", quantity=2) for i in range(6)]
    rows += [line("quiet", "quiet", "2026-10-01", hour=15)]
    result = analyze_lines(rows, date(2026, 10, 8))
    rush = result["forecast"]["rushes"][0]
    assert (rush["start"], rush["end"]) == ("12:00", "12:15")
    assert rush["expected_orders"] == 6
    assert rush["dishes"][0]["quantity"] == 12


def test_unmapped_items_and_non_synthetic_rows_fail_explicitly():
    row = line("a", "order", "2026-10-01")
    row["external_item_id"] = "unknown"
    with pytest.raises(ValueError, match="Unmapped"):
        analyze_lines([row], date(2026, 10, 8))
    row = line("a", "order", "2026-10-01")
    row["is_synthetic"] = False
    with pytest.raises(ValueError, match="synthetic"):
        analyze_lines([row], date(2026, 10, 8))


def test_repeated_line_rejected_instead_of_double_counting():
    row = line("a", "order", "2026-10-01")
    with pytest.raises(ValueError, match="Duplicate"):
        analyze_lines([row, row], date(2026, 10, 8))


def test_outlook_freezes_history_before_first_date_for_entire_span():
    rows = [
        line("thu", "thu", "2026-10-01", quantity=2),
        line("fri", "fri", "2026-10-02", source="grubhub", quantity=3),
        line("target", "target", "2026-10-08", quantity=900),
        line("nextday", "nextday", "2026-10-09", source="grubhub", quantity=1000),
    ]
    # A span longer than a week ensures Oct 15 cannot learn from Oct 8 actuals.
    result = analyze_outlook(rows, date(2026, 10, 8), days=9)
    assert len(result["days"]) == 9
    assert result["days"][0]["expected_orders"] == 1
    assert result["days"][7]["expected_orders"] == 1
    assert result["days"][7]["history_days"] == 1
    assert result["dishes"][0]["quantity"] == 10  # Thursday2 x2 + Friday3 x2
    assert result["days"][2]["history_days"] == 0
    gh = analyze_outlook(rows, date(2026, 10, 8), "grubhub", days=7)
    assert gh["days"][0]["history_days"] == 0
    assert gh["dishes"][0]["quantity"] == 3


def test_outlook_validates_span():
    with pytest.raises(ValueError, match="between 1 and 31"):
        analyze_outlook([], date(2026, 10, 8), days=0)
