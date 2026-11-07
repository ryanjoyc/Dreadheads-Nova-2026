"""Independently verify K-Station sales and measure rushes from the HTTP export.

No generator functions, recipes, inventory, operating logs, or model calls are
used. Rush figures count orders, not item lines, across the two selected feeds.
"""

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from analyze_sales_demo import analyze as reconcile
from analyze_sales_demo import records, require

START = date(2026, 10, 1)
END = date(2026, 10, 31)
SPIKE_DATE = "2026-10-21"
GROWING_ITEM = "Spicy BBQ Pork Belly Rice Bowl"
DECLINING_ITEM = "Tangy Fried Chicken Rice Bowl"
SOURCE_STORES = {("doordash", "9900201"), ("grubhub", "8800201")}


def day_type(day):
    if day.weekday() in (6, 0):
        return "quiet"
    return "normal" if day.weekday() in (1, 2) else "busy"


def validate_demand(order_rows):
    """Apply approved bounds independently of generated manifest target counts."""
    daily, hourly, quarters, source_counts = Counter(), Counter(), Counter(), Counter()
    identities = set()
    for row in order_rows:
        require(row["id"] not in identities, "Duplicate order ID")
        identities.add(row["id"])
        timestamp = datetime.fromisoformat(row["placed_at_local"])
        require(timestamp.tzinfo is None, "Expected source-local timestamp without offset")
        day = timestamp.date()
        require(START <= day <= END, "Order outside October 2026")
        require(row["timezone"] == "America/New_York", "Unexpected source timezone")
        minute = timestamp.hour * 60 + timestamp.minute
        require(660 <= minute < 960 or 1020 <= minute < 1230, "Order outside opening windows")
        ds = day.isoformat()
        daily[ds] += 1
        hourly[(ds, timestamp.hour)] += 1
        quarters[(ds, minute // 15)] += 1
        source_counts[(ds, row["source"])] += 1
    calendar = [START + timedelta(days=n) for n in range(31)]
    require(set(daily) == {d.isoformat() for d in calendar}, "Expected all 31 October dates")
    rows = []
    thursday_values, ordinary_afternoons, spike_hours = [], [], []
    recurring_dates = []
    for day in calendar:
        ds, kind = day.isoformat(), day_type(day)
        total = daily[ds]
        peak = max(hourly[(ds, h)] for h in range(24))
        low, high, peak_low, peak_high = {
            "quiet": (200, 400, 40, 75),
            "normal": (500, 650, 100, 130),
            "busy": (700, 800, 140, 150),
        }[kind]
        require(low <= total <= high, f"{ds}: daily orders outside {kind} range")
        require(peak_low <= peak <= peak_high, f"{ds}: peak hour outside {kind} range")
        if day.weekday() == 3:
            require(95 <= hourly[(ds, 14)] <= 110, f"{ds}: missing Thursday afternoon rush")
            thursday_values.append(hourly[(ds, 14)])
        else:
            require(hourly[(ds, 14)] <= 65, f"{ds}: unexpected recurring afternoon rush")
            ordinary_afternoons.append(hourly[(ds, 14)])
        if hourly[(ds, 15)] > 50:
            spike_hours.append(ds)
        if ds == SPIKE_DATE:
            require(100 <= hourly[(ds, 15)] <= 110, "Missing isolated October 21 spike")
        else:
            require(hourly[(ds, 15)] <= 50, f"{ds}: isolated spike repeats")
        if hourly[(ds, 12)] > hourly[(ds, 15)] and hourly[(ds, 18)] > hourly[(ds, 15)]:
            recurring_dates.append(ds)
        require(
            all(source_counts[(ds, s)] > 0 for s in ("doordash", "grubhub")),
            f"{ds}: both simulated feeds must contain orders",
        )
        by_hour = [{"hour": f"{h:02d}:00", "orders": hourly[(ds, h)]} for h in range(24)]
        by_quarter = [
            {"time": f"{q // 4:02d}:{q % 4 * 15:02d}", "orders": quarters[(ds, q)]}
            for q in range(96)
        ]
        require(sum(r["orders"] for r in by_quarter) == total, "Quarter-hour total mismatch")
        rows.append(
            {
                "date": ds,
                "weekday": day.strftime("%A"),
                "day_type": kind,
                "orders": total,
                "doordash_orders": source_counts[(ds, "doordash")],
                "grubhub_orders": source_counts[(ds, "grubhub")],
                "busiest_clock_hour_orders": peak,
                "busiest_clock_hours": [r["hour"] for r in by_hour if r["orders"] == peak],
                "hourly_orders": by_hour,
                "quarter_hour_orders": by_quarter,
            }
        )
    require(spike_hours == [SPIKE_DATE], "Expected exactly one isolated 15:00 spike")
    require(len(recurring_dates) >= 24, "Lunch and dinner rushes do not recur across weeks")
    require(min(thursday_values) > max(ordinary_afternoons), "Thursday rush is not distinct")
    weekday = []
    for wd in range(7):
        matching = [r for r in rows if date.fromisoformat(r["date"]).weekday() == wd]
        weekday.append(
            {
                "weekday": matching[0]["weekday"],
                "days": len(matching),
                "orders": sum(r["orders"] for r in matching),
                "orders_per_day": round(sum(r["orders"] for r in matching) / len(matching), 2),
            }
        )
    return {
        "daily": rows,
        "weekday": weekday,
        "recurring_lunch_dinner_dates": recurring_dates,
        "thursday_afternoon": {
            "dates": [r["date"] for r in rows if r["weekday"] == "Thursday"],
            "mean_orders": round(sum(thursday_values) / len(thursday_values), 2),
            "other_days_mean_orders": round(sum(ordinary_afternoons) / len(ordinary_afternoons), 2),
        },
        "isolated_spike": {"date": SPIKE_DATE, "hour": "15:00", "orders": hourly[(SPIKE_DATE, 15)]},
    }


def item_metrics(line_rows):
    weekly, weekly_units = defaultdict(Decimal), defaultdict(Decimal)
    daypart, daypart_units = defaultdict(Decimal), defaultdict(Decimal)
    for row in line_rows:
        timestamp = datetime.fromisoformat(row["placed_at_local"])
        day = timestamp.day
        period = "Oct 01–07" if day <= 7 else "Oct 25–31" if day >= 25 else None
        quantity = Decimal(str(row["quantity"]))
        if period:
            weekly[(row["item_name"], period)] += quantity
            weekly_units[period] += quantity
        part = "lunch" if timestamp.hour < 16 else "dinner"
        daypart[(row["item_name"], part)] += quantity
        daypart_units[part] += quantity
    names = sorted({name for name, _ in daypart})
    mix = []
    for name in names:
        first = 100 * weekly[(name, "Oct 01–07")] / weekly_units["Oct 01–07"]
        last = 100 * weekly[(name, "Oct 25–31")] / weekly_units["Oct 25–31"]
        mix.append(
            {
                "item_name": name,
                "first_week_units": str(weekly[(name, "Oct 01–07")]),
                "last_week_units": str(weekly[(name, "Oct 25–31")]),
                "first_week_share_pct": round(float(first), 2),
                "last_week_share_pct": round(float(last), 2),
                "change_percentage_points": round(float(last - first), 2),
                "lunch_units": str(daypart[(name, "lunch")]),
                "dinner_units": str(daypart[(name, "dinner")]),
                "lunch_share_pct": round(
                    float(100 * daypart[(name, "lunch")] / daypart_units["lunch"]), 2
                ),
                "dinner_share_pct": round(
                    float(100 * daypart[(name, "dinner")] / daypart_units["dinner"]), 2
                ),
            }
        )
    by_name = {r["item_name"]: r for r in mix}
    require(GROWING_ITEM in by_name and DECLINING_ITEM in by_name, "Missing designed dish variants")
    require(by_name[GROWING_ITEM]["change_percentage_points"] > 0, "Growing dish did not grow")
    require(
        by_name[DECLINING_ITEM]["change_percentage_points"] < 0, "Declining dish did not decline"
    )
    return mix


def analyze(dataset):
    dataset = Path(dataset)
    source_manifest = json.loads((dataset / "manifest.json").read_text())
    require(source_manifest.get("is_synthetic") is True, "Source must be labeled synthetic")
    for source in ("doordash", "grubhub"):
        entry = source_manifest["sources"][source]
        source_path = dataset / entry["path"]
        require(
            hashlib.sha256(source_path.read_bytes()).hexdigest() == entry["sha256"],
            f"{source}: generated report checksum mismatch",
        )
    baseline = reconcile(dataset, expected_store_count=2)
    exported = dataset / "backend_export"
    stores = list(records(exported / "stores.jsonl.gz"))
    require(
        {(r["source"], r["external_store_id"]) for r in stores} == SOURCE_STORES,
        "Unexpected K-Station source-store identities",
    )
    orders = list(records(exported / "orders.jsonl.gz"))
    demand = validate_demand(orders)
    mix = item_metrics(records(exported / "order_lines.jsonl.gz"))
    return {
        "is_synthetic": True,
        "verified": True,
        "date_start": START.isoformat(),
        "date_end_inclusive": END.isoformat(),
        "totals": baseline["totals"],
        "reconciliation_checks": baseline["checks"],
        **demand,
        "item_mix": mix,
        "limitations": [
            "Fabricated scenario inspired by a public campus menu; not K-Station sales evidence.",
            "Both sources are simulated. No actual provider accounts or listings were verified.",
            "Clock-hour and 15-minute figures count distinct orders across both feeds, not lines.",
            "October supplies four or five instances of each weekday, "
            "fewer than eight baseline weeks.",
            "No preparation capacity, queue/wait time, ingredient stock, "
            "or stockout inference is supported.",
            "The isolated spike has no invented cause; "
            "repeated patterns are descriptive, not causal.",
            "Item display names are deliberately configured demo variants, "
            "not verified marketplace SKUs.",
        ],
    }


def render(report):
    total = report["totals"]
    lines = [
        "# K-Station / Tartan Express: verified synthetic rush analysis",
        "",
        "Computed from the actual backend HTTP export and reconciled "
        "to the generated provider CSVs.",
        "Every sale is fabricated. This is one simulated truck with two platform feeds.",
        "",
        f"October 1–31, 2026: **{total['orders']:,} orders, {total['order_lines']:,} item lines, "
        f"{Decimal(total['quantity']):,} item units**.",
        "",
        "## Daily order volume and peak clock hour",
        "",
        "Counts below combine both feeds and count orders once, rather than counting item rows.",
        "",
        "| Date | Weekday | Type | Orders | DoorDash | Grubhub | Peak hour | Orders in peak hour |",
        "| --- | --- | --- | ---: | ---: | ---: | --- | ---: |",
    ]
    for row in report["daily"]:
        lines.append(
            f"| {row['date']} | {row['weekday']} | {row['day_type']} | {row['orders']} "
            f"| {row['doordash_orders']} | {row['grubhub_orders']} "
            f"| {', '.join(row['busiest_clock_hours'])} | {row['busiest_clock_hour_orders']} |"
        )
    thursday = report["thursday_afternoon"]
    spike = report["isolated_spike"]
    lines += [
        "",
        "## Recurring rushes and one isolated spike",
        "",
        f"- Lunch at 12:00 and dinner at 18:00 exceed the 15:00 shoulder on "
        f"{len(report['recurring_lunch_dinner_dates'])} of 31 days.",
        f"- All {len(thursday['dates'])} Thursdays have a smaller 14:00 rush: "
        f"{thursday['mean_orders']:.2f} orders on average, versus "
        f"{thursday['other_days_mean_orders']:.2f} at 14:00 on other days.",
        f"- {spike['date']} has {spike['orders']} orders at 15:00. "
        "No other day has more than 50 orders in that clock hour; treat this as one-off evidence.",
        "- No orders fall in the 16:00–17:00 break or outside 11:00–16:00 / 17:00–20:30.",
        "",
        "## Busiest 15-minute windows",
        "",
        "The full 96-bin daily curves, including zero-demand closed periods, are in analysis.json.",
        "",
        "| Date | Start | Orders in 15 minutes |",
        "| --- | --- | ---: |",
    ]
    top = sorted(
        (
            (r["date"], q["time"], q["orders"])
            for r in report["daily"]
            for q in r["quarter_hour_orders"]
        ),
        key=lambda r: (-r[2], r[0], r[1]),
    )[:8]
    lines += [f"| {ds} | {clock} | {count} |" for ds, clock, count in top]
    lines += [
        "",
        "## Changing dish mix",
        "",
        "Shares compare October 1–7 with October 25–31, "
        "rather than confusing growing volume with changing mix.",
        "",
        "| Configured demo item | First-week unit share | Last-week unit share | Change (pp) |",
        "| --- | ---: | ---: | ---: |",
    ]
    for row in report["item_mix"]:
        lines.append(
            f"| {row['item_name']} | {row['first_week_share_pct']:.2f}% "
            f"| {row['last_week_share_pct']:.2f}% | {row['change_percentage_points']:+.2f} |"
        )
    lines += [
        "",
        "## Lunch versus dinner preferences",
        "",
        "The three largest item-unit shares within each service window:",
        "",
    ]
    for part in ("lunch", "dinner"):
        best = sorted(report["item_mix"], key=lambda r: -r[f"{part}_share_pct"])[:3]
        lines.append(
            f"- {part.title()}: "
            + "; ".join(f"{r['item_name']} ({r[f'{part}_share_pct']:.2f}%)" for r in best)
        )
    lines += ["", "## Verification", ""]
    lines += [f"- {check}" for check in report["reconciliation_checks"]]
    lines += [
        "- Source report hashes, all daily ranges, peak-hour ranges, and 15-minute totals pass."
    ]
    lines += ["", "## Limitations", ""] + [f"- {s}" for s in report["limitations"]]
    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("/workspace/data/kstation_demo"))
    args = parser.parse_args()
    try:
        report = analyze(args.dataset)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        parser.exit(1, f"K-Station verification failed: {exc}\n")
    (args.dataset / "analysis.json").write_text(json.dumps(report, indent=2) + "\n")
    (args.dataset / "analysis.md").write_text(render(report))
    print(json.dumps({"verified": True, **report["totals"]}))


if __name__ == "__main__":
    main()
