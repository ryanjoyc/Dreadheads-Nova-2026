"""Reconcile a sales-only scenario with its HTTP export and report observed trends.

Uses only the two synthetic provider CSVs and the five exported sales API
collections. No generator functions, recipes, operations logs, or database reads.
"""

import argparse
import csv
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

COLLECTIONS = ("stores", "orders", "order_lines", "items", "imports")
REPORTS = {
    "doordash": (
        "doordash_order_detail.csv",
        "store_id",
        "dd_order_number",
        "order_item_quantity",
        "dd_item_id",
        "unit_price",
        "order_place_date",
        "order_place_time",
    ),
    "grubhub": (
        "grubhub_menu_line_items.csv",
        "grubhub_store_id",
        "order_uuid",
        "menu_item_quantity",
        "menu_item_id",
        "menu_item_price",
        "order_date",
        "order_time_local",
    ),
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def signature(row):
    return json.dumps(row, sort_keys=True, separators=(",", ":"))


def records(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            yield json.loads(line)


def pct(numerator, denominator):
    return round(100 * float(numerator) / float(denominator), 2) if denominator else 0.0


def per_day(count, days):
    return round(count / days, 2) if days else None


def analyze(dataset, expected_store_count=4):
    dataset = Path(dataset)
    exported = dataset / "backend_export"
    manifest = json.loads((exported / "export_manifest.json").read_text())
    require(manifest.get("is_synthetic") is True, "Export must be labeled synthetic")
    file_counts = {}
    for name in COLLECTIONS:
        filename = f"{name}.jsonl.gz"
        path = exported / filename
        metadata = manifest["files"].get(name, manifest["files"].get(filename))
        require(metadata is not None, f"Manifest missing collection {name}")
        require(
            hashlib.sha256(path.read_bytes()).hexdigest() == metadata["sha256"],
            f"Export checksum mismatch: {name}",
        )
        file_counts[name] = sum(1 for _ in records(path))
        require(file_counts[name] == metadata["rows"], f"Manifest row count mismatch: {name}")

    stores = {r["id"]: r for r in records(exported / "stores.jsonl.gz")}
    require(
        len(stores) == file_counts["stores"] == expected_store_count,
        f"Expected {expected_store_count} unique platform stores",
    )
    store_keys = {(r["source"], r["external_store_id"]) for r in stores.values()}
    require(len(store_keys) == expected_store_count, "Duplicate source-store identities")
    require({s for s, _ in store_keys} == set(REPORTS), "Both platforms are required")
    imports = {r["id"]: r for r in records(exported / "imports.jsonl.gz")}
    require(len(imports) == file_counts["imports"], "Duplicate import identities")
    require(
        all(r["is_synthetic"] and r["status"] == "succeeded" for r in imports.values()),
        "Imports must be successful and synthetic",
    )

    # These expectations are constructed independently from original CSV cells.
    raw_counts = Counter()
    raw_orders = {}
    raw_units = Decimal(0)
    for source, fields in REPORTS.items():
        filename, store_key, order_key, qty_key, *_ = fields
        with (dataset / "platform_reports" / filename).open(newline="") as stream:
            for row in csv.DictReader(stream):
                require((source, row[store_key]) in store_keys, "Raw store absent from export")
                raw_counts[(source, signature(row))] += 1
                raw_orders[(source, row[store_key], row[order_key])] = row
                raw_units += Decimal(row[qty_key])

    orders = {}
    seen_external_orders = set()
    weekday_counts = Counter()
    store_weekday = Counter()
    store_hour = Counter()
    month_platform = Counter()
    month_delivery = Counter()
    dates = []
    for row in records(exported / "orders.jsonl.gz"):
        require(row["id"] not in orders, "Duplicate exported order")
        store = stores.get(row["store_id"])
        require(store is not None, "Order has unknown store")
        key = (row["source"], row["external_store_id"], row["external_order_id"])
        require(key in raw_orders and key not in seen_external_orders, "Order identity mismatch")
        require(
            (row["source"], row["external_store_id"])
            == (store["source"], store["external_store_id"]),
            "Order source-store mismatch",
        )
        require(row["is_synthetic"] is True, "Non-synthetic order in demo export")
        require(row["last_import_run_id"] in imports, "Order has unknown import")
        raw = raw_orders[key]
        _, _, _, _, _, _, day_key, clock_key = REPORTS[row["source"]]
        require(
            row["placed_at_local"] == f"{raw[day_key]}T{raw[clock_key]}",
            "Order placement timestamp differs from CSV",
        )
        if row["source"] == "grubhub":
            require(row["subtotal"] is None, "Grubhub subtotal must remain unknown")
            require(row["order_number"] == raw["order_number"], "Grubhub order number changed")
        else:
            require(
                Decimal(row["subtotal"]) == Decimal(raw["subtotal"]), "DoorDash subtotal changed"
            )
        orders[row["id"]] = row
        seen_external_orders.add(key)
        day = date.fromisoformat(row["placed_at_local"][:10])
        month = day.isoformat()[:7]
        hour = int(row["placed_at_local"][11:13])
        dates.append(day)
        weekday_counts[day.weekday()] += 1
        store_weekday[(row["store_id"], day.weekday())] += 1
        store_hour[(row["store_id"], hour)] += 1
        month_platform[(month, row["source"])] += 1
        month_delivery[(month, row["fulfillment"])] += 1
    require(seen_external_orders == set(raw_orders), "Export omitted raw orders")
    require(bool(dates), "Cannot analyze an empty scenario")
    start, end = min(dates), max(dates)
    calendar = [start + timedelta(days=n) for n in range((end - start).days + 1)]
    calendar_weekdays = Counter(d.weekday() for d in calendar)
    calendar_months = Counter(d.isoformat()[:7] for d in calendar)

    observed_raw = Counter()
    units = Decimal(0)
    line_ids = set()
    order_line_ids = set()
    item_month = defaultdict(Decimal)
    month_units = defaultdict(Decimal)
    item_names = set()
    for row in records(exported / "order_lines.jsonl.gz"):
        require(row["id"] not in line_ids, "Duplicate exported line")
        line_ids.add(row["id"])
        require(row["order_id"] in orders, "Line has unknown order")
        order = orders[row["order_id"]]
        require(row["is_synthetic"] is True, "Non-synthetic item line")
        for key in (
            "source",
            "store_id",
            "external_store_id",
            "external_order_id",
            "placed_at_local",
        ):
            require(row[key] == order[key], f"Line/order {key} mismatch")
        require(row["last_import_run_id"] == order["last_import_run_id"], "Line import mismatch")
        raw = row["source_details"]["raw_row"]
        source = row["source"]
        fields = REPORTS[source]
        require(
            (raw[fields[1]], raw[fields[2]])
            == (row["external_store_id"], row["external_order_id"]),
            "Original row is attached to the wrong order",
        )
        require(row["external_item_id"] == raw[fields[4]], "Item ID changed")
        require(Decimal(str(row["quantity"])) == Decimal(raw[fields[3]]), "Line quantity changed")
        require(Decimal(row["unit_price"]) == Decimal(raw[fields[5]]), "Line unit price changed")
        if source == "doordash":
            require(row["modifiers"] is None, "DoorDash modifiers were invented")
            require(row["external_line_id"] == raw["order_item_id"], "DoorDash line ID changed")
        else:
            require(row["external_line_id"] is None, "Grubhub external line ID was invented")
            require(
                row["modifiers"] == json.loads(raw["menu_item_modifiers"]),
                "Grubhub modifiers changed",
            )
        observed_raw[(source, signature(raw))] += 1
        quantity = Decimal(str(row["quantity"]))
        units += quantity
        month = row["placed_at_local"][:7]
        # Names are only display-level groups; this does not create canonical IDs.
        item_month[(row["item_name"], month)] += quantity
        month_units[month] += quantity
        item_names.add(row["item_name"])
        order_line_ids.add(row["order_id"])
    require(observed_raw == raw_counts, "Original CSV rows differ from exported source rows")
    require(order_line_ids == set(orders), "An exported order has no item lines")
    require(units == raw_units, "Summed quantity differs from CSV")
    require(manifest["totals"]["orders"] == len(orders), "Manifest order total differs")
    require(manifest["totals"]["order_lines"] == len(line_ids), "Manifest line total differs")
    require(Decimal(str(manifest["totals"]["quantity"])) == units, "Manifest quantity differs")

    expected_items = set()
    for source, raw_signature in raw_counts:
        raw = json.loads(raw_signature)
        fields = REPORTS[source]
        expected_items.add((source, raw[fields[1]], raw[fields[4]]))
    observed_items = set()
    for row in records(exported / "items.jsonl.gz"):
        require(row["is_synthetic"] is True, "Non-synthetic observed item")
        observed_items.add((row["source"], row["external_store_id"], row["external_item_id"]))
    require(len(observed_items) == file_counts["items"], "Duplicate observed item identity")
    require(expected_items == observed_items, "Observed item listing differs from raw reports")

    months = sorted(calendar_months)
    monthly = []
    for month in months:
        dd, gh = month_platform[(month, "doordash")], month_platform[(month, "grubhub")]
        monthly.append(
            {
                "month": month,
                "orders": dd + gh,
                "orders_per_calendar_day": round((dd + gh) / calendar_months[month], 2),
                "doordash_orders": dd,
                "grubhub_orders": gh,
                "grubhub_share_pct": pct(gh, dd + gh),
                "delivery_share_pct": pct(month_delivery[(month, "delivery")], dd + gh),
            }
        )
    weekday = [
        {
            "weekday": date(2026, 6, 1 + wd).strftime("%A"),
            "calendar_days": calendar_weekdays[wd],
            "orders": weekday_counts[wd],
            "orders_per_day": per_day(weekday_counts[wd], calendar_weekdays[wd]),
        }
        for wd in range(7)
    ]
    store_metrics = []
    for store_id, store in sorted(
        stores.items(), key=lambda pair: (pair[1]["store_name"], pair[1]["source"])
    ):
        by_hour = [{"hour": h, "orders": store_hour[(store_id, h)]} for h in range(24)]
        count = sum(v["orders"] for v in by_hour)
        store_metrics.append(
            {
                "source": store["source"],
                "external_store_id": store["external_store_id"],
                "store_name": store["store_name"],
                "orders": count,
                "orders_per_calendar_day": round(count / len(calendar), 2),
                "weekday_orders_per_day": [
                    {
                        "weekday": weekday[wd]["weekday"],
                        "orders_per_day": per_day(
                            store_weekday[(store_id, wd)], calendar_weekdays[wd]
                        ),
                    }
                    for wd in range(7)
                ],
                "orders_by_hour": by_hour,
            }
        )
    items = [
        {
            "item_name": name,
            "monthly": [
                {
                    "month": month,
                    "units": str(item_month[(name, month)]),
                    "share_of_item_units_pct": pct(item_month[(name, month)], month_units[month]),
                }
                for month in months
            ],
        }
        for name in sorted(item_names)
    ]
    return {
        "is_synthetic": True,
        "verified": True,
        "date_start": start.isoformat(),
        "date_end_inclusive": end.isoformat(),
        "calendar_days": len(calendar),
        "totals": {
            "stores": len(stores),
            "orders": len(orders),
            "order_lines": len(line_ids),
            "quantity": str(units),
        },
        "checks": [
            "All exported file hashes and row counts match the export manifest.",
            "Every original CSV row is preserved exactly in exported source details.",
            "Store-scoped order IDs, quantities, prices, local times and modifiers reconcile.",
            "All records carrying a synthetic flag are synthetic; imports succeeded.",
            "Observed platform item identities reconcile without inventing canonical mappings.",
        ],
        "weekday_demand": weekday,
        "monthly_platform_and_fulfillment": monthly,
        "platform_stores": store_metrics,
        "item_mix_by_display_name": items,
        "limitations": [
            "Synthetic designed patterns support demos, not real-world accuracy claims.",
            "Calendar-day rates include all dates in the observed range; "
            "they do not establish store opening hours or report completeness.",
            "Item display-name grouping is an analysis convenience, "
            "not an approved cross-platform identity mapping.",
            "No recipe, inventory, stockout, staffing, weather, or event evidence is present.",
        ],
    }


def render(report):
    total = report["totals"]
    lines = [
        "# Synthetic sales demo: verified example analysis",
        "",
        "All figures below are calculated from the actual backend API export, "
        "after reconciliation to the two generated provider reports.",
        "This is fabricated sales data for demonstration. Designed patterns are "
        "not evidence of real demand, stockouts, or business outcomes.",
        "",
        f"Coverage: {report['date_start']}–{report['date_end_inclusive']} "
        f"({report['calendar_days']} calendar days).",
        f"Totals: {total['stores']:,} platform stores, {total['orders']:,} orders, "
        f"{total['order_lines']:,} item lines, {Decimal(total['quantity']):,} units.",
        "",
        "## Weekday demand",
        "",
        "Compare daily averages rather than raw totals, because the range "
        "contains different numbers of each weekday.",
        "",
        "| Weekday | Calendar days | Orders | Orders/day |",
        "| --- | ---: | ---: | ---: |",
    ]
    for row in report["weekday_demand"]:
        rate = "—" if row["orders_per_day"] is None else f"{row['orders_per_day']:.2f}"
        lines.append(f"| {row['weekday']} | {row['calendar_days']} | {row['orders']:,} | {rate} |")
    lines += [
        "",
        "## Monthly platform and fulfillment trends",
        "",
        "| Month | Orders/day | Grubhub order share | Delivery order share |",
        "| --- | ---: | ---: | ---: |",
    ]
    for row in report["monthly_platform_and_fulfillment"]:
        lines.append(
            f"| {row['month']} | {row['orders_per_calendar_day']:.2f} "
            f"| {row['grubhub_share_pct']:.2f}% | {row['delivery_share_pct']:.2f}% |"
        )
    lines += [
        "",
        "## Store/platform demand",
        "",
        "These rows preserve each platform's store identity. Repeated display "
        "names do not create a canonical restaurant mapping.",
        "",
        "| Store | Platform | Orders/day | Three busiest clock hours |",
        "| --- | --- | ---: | --- |",
    ]
    for row in report["platform_stores"]:
        peak = sorted(row["orders_by_hour"], key=lambda x: (-x["orders"], x["hour"]))[:3]
        labels = ", ".join(f"{r['hour']:02d}:00 ({r['orders']:,} orders)" for r in peak)
        lines.append(
            f"| {row['store_name']} | {row['source']} "
            f"| {row['orders_per_calendar_day']:.2f} | {labels} |"
        )
    lines += [
        "",
        "## Changing item mix",
        "",
        "Compare each display name's share of item units in the first and last "
        "months. These are observed sales shares, not causal explanations.",
        "",
        "| Item display name | First month share | Last month share | Change (percentage points) |",
        "| --- | ---: | ---: | ---: |",
    ]
    for row in report["item_mix_by_display_name"]:
        first = row["monthly"][0]["share_of_item_units_pct"]
        last = row["monthly"][-1]["share_of_item_units_pct"]
        lines.append(f"| {row['item_name']} | {first:.2f}% | {last:.2f}% | {last - first:+.2f} |")
    lines += ["", "## Reconciliation", ""] + [f"- {check}" for check in report["checks"]]
    lines += ["", "## Boundaries", ""] + [f"- {item}" for item in report["limitations"]]
    lines += [
        "",
        "For additional examples, use `analysis.json` for all monthly item shares, "
        "platform-store hourly counts, and weekday daily averages.",
        "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("/workspace/data/sales_only_demo"))
    args = parser.parse_args()
    try:
        report = analyze(args.dataset)
    except (ValueError, KeyError, OSError, TypeError) as exc:
        parser.exit(1, f"Analysis verification failed: {exc}\n")
    (args.dataset / "analysis.json").write_text(json.dumps(report, indent=2) + "\n")
    (args.dataset / "analysis.md").write_text(render(report))
    print(json.dumps({"verified": True, **report["totals"]}))


if __name__ == "__main__":
    main()
