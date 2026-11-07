"""The request-local agent tools cannot escape their historical sales snapshot."""

from datetime import date, datetime

import pytest

from nova_backend.rush import Forecast
from nova_backend.schemas import RushParams
from nova_backend.tablet_tools import TabletTools


def row(identity, day, *, source="doordash", hour=12, quantity=1, order=None):
    return {
        "id": identity,
        "order_id": order or identity,
        "source": source,
        "store_id": "00000000-0000-0000-0000-000000000001",
        "external_store_id": {"doordash": "9900201", "grubhub": "8800201"}[source],
        "external_item_id": "0099020001" if source == "doordash" else "KS-M01",
        "placed_at_local": datetime.fromisoformat(f"{day}T{hour:02d}:00:00"),
        "quantity": quantity,
        "is_synthetic": True,
    }


def tools(rows, **kwargs):
    params = RushParams(date=date(2026, 10, 15), **kwargs)
    return TabletTools(rows, params, Forecast(params.on_date, 15))


def test_tools_count_distinct_orders_and_map_both_platform_items():
    tool = tools(
        [
            row("a", "2026-10-01", order="dd", quantity=2),
            row("b", "2026-10-01", order="dd", quantity=3),
            row("c", "2026-10-01", source="grubhub", quantity=4),
        ]
    )
    args = {"date_start": "2026-10-01", "date_end": "2026-10-02"}
    assert tool.count_orders(args) == {"orders": 2, "days": 1}
    ranked = tool.get_top_dishes(args)["dishes"]
    assert len(ranked) == 1
    assert ranked[0]["units"] == 9
    assert ranked[0]["orders"] == 2
    assert tool.get_day_traffic({"date": "2026-10-01"})["total_orders"] == 2


def test_target_future_and_out_of_range_access_are_blocked():
    tool = tools(
        [row("past", "2026-10-08"), row("target", "2026-10-15"), row("future", "2026-10-22")]
    )
    assert len(tool.rows) == 1
    with pytest.raises(ValueError, match="before"):
        tool.get_day_traffic({"date": "2026-10-15"})
    args = {"date_start": "2026-10-01", "date_end": "2026-10-16"}
    with pytest.raises(ValueError, match="date_start"):
        tool.count_orders(args)
    with pytest.raises(ValueError, match="62"):
        tool.count_orders({"date_start": "2026-01-01", "date_end": "2026-10-15"})
    _args, result = tool.run("get_day_traffic", '{"date":"2026-10-15"}')
    assert "error" in result


def test_snapshot_rejects_wrong_cohort_or_unlabeled_real_sales():
    bad = row("bad", "2026-10-01")
    bad["external_store_id"] = "unrelated"
    with pytest.raises(ValueError, match="cohort"):
        tools([bad])
    bad = row("bad", "2026-10-01")
    bad["is_synthetic"] = False
    with pytest.raises(ValueError, match="synthetic"):
        tools([bad])


def test_source_clock_and_dish_filters_stay_inside_snapshot():
    tool = tools(
        [
            row("dd", "2026-10-01"),
            row("gh", "2026-10-01", source="grubhub"),
            row("late", "2026-10-01", source="grubhub", hour=23),
        ],
        source="grubhub",
    )
    base = {"date_start": "2026-10-01", "date_end": "2026-10-02"}
    assert tool.count_orders(base)["orders"] == 2
    assert tool.count_orders(base | {"time_start": "22:00", "time_end": "02:00"})["orders"] == 1
    assert tool.count_orders(base | {"item_name": "not a dish"})["orders"] == 0


def test_forecast_week_limit_uses_only_requested_past_weekdays():
    tool = tools(
        [
            row("old", "2026-10-01", quantity=20),
            row("recent", "2026-10-08"),
            row("target", "2026-10-15"),
        ]
    )
    fc = tool.get_rush_forecast({"weeks": 1})
    assert fc["history_days"] == ["2026-10-08"]
    assert fc["expected_by_slot"]["12:00"] == 1
    assert set(tool.get_rush_forecast({"weeks": 2})["history_days"]) == {"2026-10-01", "2026-10-08"}
    with pytest.raises(ValueError, match="1-26"):
        tool.get_rush_forecast({"weeks": 27})
