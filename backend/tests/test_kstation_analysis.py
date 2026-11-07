"""Independent demand checks use explicit profiles, not the scenario generator."""

import importlib.util
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

script_dir = Path(__file__).resolve().parents[1] / "scripts"
spec = importlib.util.spec_from_file_location(
    "analyze_kstation", script_dir / "analyze_kstation.py"
)
analysis = importlib.util.module_from_spec(spec)
sys.path.insert(0, str(script_dir))
try:
    spec.loader.exec_module(analysis)
finally:
    sys.path.pop(0)


def scenario_orders():
    records = []
    for offset in range(31):
        day = date(2026, 10, 1) + timedelta(days=offset)
        kind = analysis.day_type(day)
        profile = {
            "quiet": {11: 35, 12: 70, 13: 40, 14: 30, 15: 15, 17: 20, 18: 65, 19: 15, 20: 10},
            "normal": {11: 70, 12: 125, 13: 90, 14: 50, 15: 25, 17: 55, 18: 120, 19: 30, 20: 10},
            "busy": {11: 100, 12: 150, 13: 110, 14: 65, 15: 40, 17: 70, 18: 145, 19: 50, 20: 20},
        }[kind].copy()
        if day.weekday() == 3:
            profile.update({11: 85, 13: 90, 14: 100})
        if day.isoformat() == "2026-10-21":
            profile.update({11: 40, 13: 60, 15: 105, 17: 35})
        for hour, count in profile.items():
            for number in range(count):
                records.append(
                    {
                        "id": f"{day}-{hour}-{number}",
                        "placed_at_local": f"{day}T{hour:02d}:00:{number % 60:02d}",
                        "timezone": "America/New_York",
                        "source": "doordash" if number % 2 else "grubhub",
                    }
                )
    return records


def test_valid_demand_counts_combined_sources_and_calendar_days():
    report = analysis.validate_demand(scenario_orders())
    assert len(report["daily"]) == 31
    assert sum(row["orders"] for row in report["daily"]) == 18250
    assert report["isolated_spike"]["orders"] == 105
    assert report["thursday_afternoon"]["mean_orders"] == 100
    assert len(report["thursday_afternoon"]["dates"]) == 5
    assert len(report["recurring_lunch_dinner_dates"]) == 31
    assert sum(row["days"] for row in report["weekday"]) == 31
    assert all(len(row["quarter_hour_orders"]) == 96 for row in report["daily"])


@pytest.mark.parametrize("clock", ["10:59:59", "16:00:00", "16:59:59", "20:30:00"])
def test_closed_window_rejected(clock):
    rows = scenario_orders()
    rows[0]["placed_at_local"] = "2026-10-01T" + clock
    with pytest.raises(ValueError, match="opening windows"):
        analysis.validate_demand(rows)


def test_duplicate_orders_rejected_instead_of_counted_twice():
    rows = scenario_orders()
    with pytest.raises(ValueError, match="Duplicate order"):
        analysis.validate_demand(rows + [rows[0]])


def test_wrong_daily_range_rejected():
    rows = scenario_orders()
    first_quiet = [r for r in rows if r["placed_at_local"].startswith("2026-10-04")][:199]
    rows = [r for r in rows if not r["placed_at_local"].startswith("2026-10-04")] + first_quiet
    with pytest.raises(ValueError, match="daily orders"):
        analysis.validate_demand(rows)


def test_a_second_isolated_spike_is_rejected():
    rows = scenario_orders()
    changed = 0
    for row in rows:
        if row["placed_at_local"].startswith("2026-10-07T11") and changed < 26:
            row["placed_at_local"] = "2026-10-07T15:05:00"
            changed += 1
    with pytest.raises(ValueError, match="isolated spike repeats"):
        analysis.validate_demand(rows)
