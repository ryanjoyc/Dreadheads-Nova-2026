"""Generate reproducible sales-only demo reports accepted by the current importers.

All observations are fabricated. Format compatibility is not evidence of actual
provider semantics, merchant authorization, or real-world predictive accuracy.
"""

import argparse
import csv
import hashlib
import json
import random
from collections import Counter
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid5
from zoneinfo import ZoneInfo

START = date(2026, 5, 1)
END = date(2026, 10, 31)
NAMESPACE = UUID("9db40000-0000-4000-8000-000000000001")
TIMEZONE = "America/New_York"
DD_HEADERS = [
    "business_id",
    "store_id",
    "business_name",
    "store_name",
    "dd_order_number",
    "order_place_date",
    "order_place_time",
    "created_at",
    "timezone",
    "dd_item_id",
    "item_merchant_supplied_id",
    "order_item_id",
    "item_name",
    "category_name",
    "menu_name",
    "order_item_quantity",
    "unit_price",
    "original_item_price",
    "subtotal",
    "is_consumer_pickup",
    "dashpass",
    "mx_order_number",
    "external_order_id",
]
GH_HEADERS = [
    "grubhub_store_id",
    "store_name",
    "store_number",
    "external_id",
    "order_number",
    "order_uuid",
    "partner_order_id",
    "order_date",
    "order_time_local",
    "order_time_zone",
    "menu_item_id",
    "menu_item_name",
    "menu_item_category_name",
    "menu_item_quantity",
    "menu_item_price",
    "menu_item_modifiers",
    "fullfillment_type",
]
STORES = [
    {"label": "Uptown", "doordash": "9900101", "grubhub": "8800101"},
    {"label": "Market", "doordash": "9900102", "grubhub": "8800102"},
]
# Item IDs, names, categories, and prices are synthetic menu labels, not recipes.
MENU = [
    ("SYN-M01", "Citrus Grain Bowl", "Bowls", "13.50"),
    ("SYN-M02", "Roast Beef Sandwich", "Sandwiches", "12.50"),
    ("SYN-M03", "Turkey Club", "Sandwiches", "11.75"),
    ("SYN-M04", "Breakfast Bagel", "Breakfast", "8.50"),
    ("SYN-M05", "Weekend Pancakes", "Breakfast", "10.00"),
    ("SYN-M06", "Chicken Wrap", "Wraps", "11.00"),
    ("SYN-M07", "Veggie Wrap", "Wraps", "10.50"),
    ("SYN-M08", "Tomato Soup", "Soups", "6.50"),
    ("SYN-M09", "Garden Salad", "Salads", "9.50"),
    ("SYN-M10", "Crispy Fries", "Sides", "4.50"),
    ("SYN-M11", "Iced Tea", "Drinks", "3.00"),
    ("SYN-M12", "Coffee", "Drinks", "3.50"),
    ("SYN-M13", "Chocolate Cookie", "Desserts", "2.50"),
    ("SYN-M14", "Spicy Chicken Sandwich", "Sandwiches", "12.75"),
    ("SYN-M15", "Fruit Cup", "Sides", "4.00"),
]


def _calendar():
    contexts, weights = [], []
    for offset in range((END - START).days + 1):
        day = START + timedelta(days=offset)
        progress = offset / ((END - START).days)
        for store in range(2):
            weekday_factor = (
                (1.55 if day.weekday() >= 5 else 0.85)
                if store == 0
                else (0.65 if day.weekday() >= 5 else 1.35)
            )
            contexts.append((day, store, progress))
            weights.append(weekday_factor * (0.85 + 0.35 * progress))
    return contexts, weights


def _placed_at(rng, day, store):
    weekend = day.weekday() >= 5
    # Named groups only control fabricated order placement distributions.
    if store == 1 and not weekend:
        group_weights = [0.10, 0.65, 0.10, 0.15]
    elif store == 0:
        group_weights = [0.22 if weekend else 0.08, 0.24, 0.08, 0.55]
    else:
        group_weights = [0.35, 0.35, 0.10, 0.20]
    group = rng.choices(range(4), group_weights)[0]
    ranges = [(8, 11), (11, 14), (14, 17), (17, 22)]
    start, end = ranges[group]
    hour = rng.randrange(start, end)
    return datetime.combine(day, time(hour, rng.randrange(60), rng.randrange(60)))


def _item_weights(timestamp, progress):
    morning = timestamp.hour < 11
    weekend = timestamp.weekday() >= 5
    dinner = timestamp.hour >= 17
    return [
        0.35 + 4.0 * progress,
        3.8 - 3.2 * progress,
        1.8,
        5.0 if morning else 0.15,
        8.0 if morning and weekend else (1.0 if morning else 0.03),
        1.7,
        1.1,
        0.7,
        1.3,
        2.5 if dinner else 1.3,
        1.2,
        3.0 if morning else 0.25,
        1.0,
        2.8 if dinner else 0.9,
        0.8,
    ]


def _money(value):
    return f"{value:.2f}"


def generate(output_dir: Path, orders: int = 45000, seed: int = 20261107) -> dict:
    """Write exact supported report columns and a deterministic synthetic manifest.

    Refuses a nonempty destination; callers must choose a separate output folder
    instead of overwriting either the existing sample data or previous artifacts.
    """
    output_dir = Path(output_dir)
    if isinstance(orders, bool) or not isinstance(orders, int) or orders < 1:
        raise ValueError("orders must be a positive integer")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("Output directory must be empty; existing files are preserved")
    rng = random.Random(seed)
    contexts, weights = _calendar()
    selected = rng.choices(contexts, weights, k=orders)
    scheduled = [(*context, _placed_at(rng, context[0], context[1])) for context in selected]
    scheduled.sort(key=lambda row: (row[0], row[3], row[1]))
    report_dir = output_dir / "platform_reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "doordash": report_dir / "doordash_order_detail.csv",
        "grubhub": report_dir / "grubhub_menu_line_items.csv",
    }
    counts = {source: Counter() for source in paths}
    order_dates = {source: [] for source in paths}
    with (
        paths["doordash"].open("w", newline="", encoding="utf-8") as dd_file,
        paths["grubhub"].open("w", newline="", encoding="utf-8") as gh_file,
    ):
        writers = {
            "doordash": csv.DictWriter(dd_file, fieldnames=DD_HEADERS, lineterminator="\n"),
            "grubhub": csv.DictWriter(gh_file, fieldnames=GH_HEADERS, lineterminator="\n"),
        }
        for writer in writers.values():
            writer.writeheader()
        for serial, (day, location, progress, timestamp) in enumerate(scheduled, 1):
            store = STORES[location]
            gh_probability = 0.20 + 0.45 * progress + (0.08 if location == 0 else 0.0)
            source = "grubhub" if rng.random() < gh_probability else "doordash"
            order_dates[source].append(day)
            counts[source]["orders"] += 1
            order_id = f"synthetic-demo-v1-{source}-{serial:08d}"
            pickup = rng.random() < (0.12 if timestamp.hour >= 17 else 0.30)
            pos_id = f"SYN-POS-{serial:08d}" if rng.random() >= 0.12 else ""
            line_count = rng.choices([1, 2, 3, 4], [0.40, 0.36, 0.18, 0.06])[0]
            chosen = rng.choices(range(len(MENU)), _item_weights(timestamp, progress), k=line_count)
            lines = []
            for index, item_number in enumerate(chosen, 1):
                item_id, name, category, base_price = MENU[item_number]
                base = Decimal(base_price)
                quantity = rng.choices([1, 2, 3], [0.86, 0.12, 0.02])[0]
                extra = rng.random() < 0.18 and category not in {"Drinks", "Desserts"}
                upcharge = Decimal("1.50") if extra else Decimal(0)
                mods = (
                    [{"id": "SYN-EXTRA", "name": "Extra topping", "price": 1.5, "quantity": 1}]
                    if extra
                    else []
                )
                lines.append(
                    (index, item_number, item_id, name, category, base, quantity, upcharge, mods)
                )
            subtotal = sum((line[5] + line[7]) * line[6] for line in lines)
            for index, item_number, item_id, name, category, base, qty, upcharge, mods in lines:
                counts[source]["lines"] += 1
                counts[source]["quantity"] += qty
                if source == "doordash":
                    row = {
                        "business_id": "9900001",
                        "store_id": store[source],
                        "business_name": "Harbor Deli (SYNTHETIC)",
                        "store_name": f"Harbor Deli - {store['label']} (SYNTHETIC)",
                        "dd_order_number": order_id,
                        "order_place_date": day.isoformat(),
                        "order_place_time": timestamp.time().isoformat(),
                        "created_at": timestamp.replace(tzinfo=ZoneInfo(TIMEZONE))
                        .astimezone(UTC)
                        .isoformat()
                        .replace("+00:00", "Z"),
                        "timezone": TIMEZONE,
                        "dd_item_id": f"009900{item_number + 1:04d}",
                        "item_merchant_supplied_id": item_id,
                        "order_item_id": f"{order_id}-line-{index}",
                        "item_name": name,
                        "category_name": category,
                        "menu_name": "Synthetic Sales Menu",
                        "order_item_quantity": qty,
                        "unit_price": _money(base + upcharge),
                        "original_item_price": _money(base),
                        "subtotal": _money(subtotal),
                        "is_consumer_pickup": str(pickup),
                        "dashpass": str(serial % 3 != 0),
                        "mx_order_number": f"{serial:08d}" if pos_id else "",
                        "external_order_id": pos_id,
                    }
                else:
                    row = {
                        "grubhub_store_id": store[source],
                        "store_name": f"Harbor Deli - {store['label']} (SYNTHETIC)",
                        "store_number": f"{location + 1:03d}",
                        "external_id": f"SYN-STORE-{location + 1:03d}",
                        "order_number": order_id,
                        "order_uuid": str(uuid5(NAMESPACE, order_id)),
                        "partner_order_id": pos_id,
                        "order_date": day.isoformat(),
                        "order_time_local": timestamp.time().isoformat(),
                        "order_time_zone": TIMEZONE,
                        "menu_item_id": item_id,
                        "menu_item_name": name,
                        "menu_item_category_name": category,
                        "menu_item_quantity": qty,
                        "menu_item_price": _money(base),
                        "menu_item_modifiers": json.dumps(mods, separators=(",", ":")),
                        "fullfillment_type": "PICKUP" if pickup else "DELIVERY",
                    }
                writers[source].writerow(row)
    manifests = {}
    for source, path in paths.items():
        manifests[source] = {
            **dict(counts[source]),
            "path": str(path.relative_to(output_dir)),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "store_ids": [store[source] for store in STORES],
            "observed_date_start": min(order_dates[source]).isoformat()
            if order_dates[source]
            else None,
            "observed_date_end": max(order_dates[source]).isoformat()
            if order_dates[source]
            else None,
            "columns": DD_HEADERS if source == "doordash" else GH_HEADERS,
        }
    manifest = {
        "dataset": "synthetic-demo-v1",
        "is_synthetic": True,
        "seed": seed,
        "orders": orders,
        "date_start": START.isoformat(),
        "date_end_inclusive": END.isoformat(),
        "timezone": TIMEZONE,
        "sources": manifests,
        "designed_patterns": [
            "Market weekday lunch concentration; Uptown dinner concentration",
            "Uptown weekends stronger; Market weekdays stronger",
            "Citrus Grain Bowl rising; Roast Beef Sandwich declining over six months",
            "Grubhub order share rises from early to late months",
            "Weekend Pancakes concentrate in weekend mornings",
            "Pickup share is lower in evening orders",
        ],
        "assumptions": [
            "All data is fabricated; no provider accounts or APIs were contacted.",
            "Only documented report columns consumed by the current backend are written.",
            "Prices are USD decimals; synthetic DoorDash unit_price includes add-on upcharges.",
            "Synthetic Grubhub menu_item_price is the base price and modifiers are a JSON array.",
            "No recipes, inventory, operating logs, weather/event claims, or inferred costs.",
            "Both sources contain complete orders; no cancellations, refunds, or scheduled orders.",
            "Placement dates/times use America/New_York; created_at is UTC.",
            "No actual-export compatibility or predictive-accuracy guarantee is implied.",
        ],
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--orders", type=int, default=45000)
    parser.add_argument("--seed", type=int, default=20261107)
    args = parser.parse_args()
    try:
        result = generate(args.out, args.orders, args.seed)
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Generation failed: {exc}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
