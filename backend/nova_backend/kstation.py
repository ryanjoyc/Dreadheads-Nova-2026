"""Reproducible October K-Station / Tartan Express synthetic sales scenario.

Public menu inspiration is not evidence of actual products, prices, sales,
platform participation, or historical opening hours at the campus food truck.
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

from nova_backend.synthetic import DD_HEADERS, GH_HEADERS

START = date(2026, 10, 1)
END = date(2026, 10, 31)
TIMEZONE = "America/New_York"
STORE_NAME = "Tartan Express - K-Station (SYNTHETIC)"
STORE_IDS = {"doordash": "9900201", "grubhub": "8800201"}
NAMESPACE = UUID("63b96299-332e-4405-b8ec-10d8709ce890")
MENU_SOURCE = (
    "https://apps.studentaffairs.cmu.edu/dining/dashboard_images/Production/menus/206/KS%2010.1.pdf"
)
HOURS_SOURCE = "https://apps.studentaffairs.cmu.edu/dining/conceptinfo"
DAY_TYPES = {
    "quiet": {"orders": (200, 400), "peak": (40, 75)},
    "normal": {"orders": (500, 650), "peak": (100, 130)},
    "busy": {"orders": (700, 800), "peak": (140, 150)},
}
# Configured listings are synthetic flattened choices, not verified Grubhub SKUs.
# Tuple: canonical synthetic ID, name, category, lunch price, dinner price.
MENU = [
    ("KS-M01", "Tangy Fried Chicken Rice Bowl", "Rice Bowls", "14.00", "16.00"),
    ("KS-M02", "OG Gochujang Chicken Rice Bowl", "Rice Bowls", "14.00", "16.00"),
    ("KS-M03", "Spicy BBQ Pork Belly Rice Bowl", "Rice Bowls", "14.00", "16.00"),
    ("KS-M04", "Bulgogi Beef Rice Bowl", "Rice Bowls", "15.00", "17.00"),
    ("KS-M05", "Korean BBQ Chicken Rice Bowl", "Rice Bowls", "14.00", "16.00"),
    ("KS-M06", "Mandoo Rice Bowl", "Rice Bowls", "14.00", "16.00"),
    ("KS-M07", "Tangy Fried Chicken Salad Bowl", "Salad Bowls", "14.00", "16.00"),
    ("KS-M08", "OG Gochujang Chicken Salad Bowl", "Salad Bowls", "14.00", "16.00"),
    ("KS-M09", "Spicy BBQ Pork Belly Salad Bowl", "Salad Bowls", "14.00", "16.00"),
    ("KS-M10", "Bulgogi Beef Salad Bowl", "Salad Bowls", "15.00", "17.00"),
    ("KS-M11", "K-Signature Bowl", "Signature Items", "14.00", "16.00"),
    ("KS-M12", "The Original Kimchi Fries", "Signature Items", "14.50", "16.50"),
    ("KS-M13", "Side Rice", "Sides", "3.50", "3.50"),
    ("KS-M14", "Side Fries", "Sides", "3.50", "3.50"),
    ("KS-M15", "Kimchi (4 oz)", "Sides", "3.50", "3.50"),
    ("KS-M16", "Mandoo (6 pieces)", "Sides", "5.50", "5.50"),
    ("KS-M17", "Ginger Salad", "Sides", "5.50", "5.50"),
    ("KS-M18", "Pepsi Can", "Drinks", "2.00", "2.00"),
    ("KS-M19", "Strawberry Ade Pouch", "Drinks", "4.50", "4.50"),
]


def day_type(day):
    return "quiet" if day.weekday() in (0, 6) else "normal" if day.weekday() in (1, 2) else "busy"


def hourly_profile(rng, day):
    """Allocate exact counts within fixed day, peak, and off-hour constraints."""
    kind = day_type(day)
    total = rng.randint(*DAY_TYPES[kind]["orders"])
    peak = (
        rng.randint(60, 75)
        if kind == "quiet"
        else rng.randint(110, 130)
        if kind == "normal"
        else rng.randint(140, 150)
    )
    primary, secondary = (18, 12) if day.weekday() in (4, 5) else (12, 18)
    counts = {hour: 0 for hour in (11, 12, 13, 14, 15, 17, 18, 19, 20)}
    counts[primary] = peak
    counts[secondary] = peak - rng.randint(5, 8)
    fixed = {primary, secondary}
    if day.weekday() == 3:
        counts[14] = rng.randint(95, 110)
        fixed.add(14)
    if day == date(2026, 10, 21):
        counts[15] = rng.randint(100, min(110, peak - 8))
        fixed.add(15)
    caps = {hour: peak - 1 for hour in counts}
    caps[14] = 35 if kind == "quiet" else 65
    caps[15] = {"quiet": 20, "normal": 35, "busy": 45}[kind]
    caps[20] = peak // 2  # Only half an hour is open.
    weights = {11: 1.4, 13: 1.7, 14: 0.6, 15: 0.3, 17: 1.6, 19: 1.2, 20: 0.45}
    weights = {h: w * rng.uniform(0.8, 1.2) for h, w in weights.items()}
    remaining = total - sum(counts.values())
    if remaining < 0 or sum(caps[h] for h in counts if h not in fixed) < remaining:
        raise ValueError("Infeasible synthetic hourly allocation")
    for _ in range(remaining):
        available = [h for h in counts if h not in fixed and counts[h] < caps[h]]
        chosen = rng.choices(available, [weights[h] for h in available])[0]
        counts[chosen] += 1
    return kind, total, peak, counts


def item_weights(timestamp):
    progress = (timestamp.day - 1) / 30
    dinner = timestamp.hour >= 17
    rice = 0.6 if dinner else 1.8
    salad = 2.2 if dinner else 0.6
    return [
        (5.2 - 4.5 * progress) * rice,
        2.0 * rice,
        (0.5 + 5.5 * progress) * rice,
        2.2 * rice,
        1.5 * rice,
        0.8 * rice,
        1.4 * salad,
        1.7 * salad,
        1.5 * salad,
        1.6 * salad,
        2.1,
        2.4 if dinner else 1.1,
        0.35,
        0.8,
        0.65,
        0.8,
        0.45,
        1.4,
        0.8,
    ]


def money(value):
    return f"{value:.2f}"


def generate(output_dir: Path, seed: int = 20261107) -> dict:
    output_dir = Path(output_dir)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("Output directory must be empty; existing files are preserved")
    rng = random.Random(seed)
    daily = []
    scheduled = []
    for offset in range(31):
        day = START + timedelta(days=offset)
        kind, total, peak, hours = hourly_profile(rng, day)
        quarters = Counter()
        for hour, count in hours.items():
            for _ in range(count):
                quarter = (
                    rng.choices([0, 1], [0.55, 0.45])[0]
                    if hour == 20
                    else rng.choices([0, 1, 2, 3], [0.16, 0.29, 0.34, 0.21])[0]
                )
                minute = quarter * 15 + rng.randrange(15)
                timestamp = datetime.combine(day, time(hour, minute, rng.randrange(60)))
                scheduled.append(timestamp)
                quarters[f"{hour:02d}:{quarter * 15:02d}"] += 1
        daily.append(
            {
                "date": day.isoformat(),
                "day_type": kind,
                "target_orders": total,
                "target_peak_hour_orders": peak,
                "hourly_orders": {str(h): n for h, n in hours.items()},
                "quarter_hour_orders": dict(sorted(quarters.items())),
                "orders_by_source": {"doordash": 0, "grubhub": 0},
            }
        )
    scheduled.sort()
    report_dir = output_dir / "platform_reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "doordash": report_dir / "doordash_order_detail.csv",
        "grubhub": report_dir / "grubhub_menu_line_items.csv",
    }
    counters = {s: Counter(orders=0, lines=0, quantity=0) for s in paths}
    with (
        paths["doordash"].open("w", newline="", encoding="utf-8") as dd,
        paths["grubhub"].open("w", newline="", encoding="utf-8") as gh,
    ):
        writers = {
            "doordash": csv.DictWriter(dd, DD_HEADERS, lineterminator="\n"),
            "grubhub": csv.DictWriter(gh, GH_HEADERS, lineterminator="\n"),
        }
        for writer in writers.values():
            writer.writeheader()
        for serial, timestamp in enumerate(scheduled, 1):
            source = "grubhub" if rng.random() < 0.6 else "doordash"
            order_id = f"KS-SYN-{source}-{serial:08d}"
            counters[source]["orders"] += 1
            daily[timestamp.day - 1]["orders_by_source"][source] += 1
            pos_id = f"KS-SYN-POS-{serial:08d}" if rng.random() > 0.14 else ""
            pickup = rng.random() < 0.92
            number_of_lines = rng.choices([1, 2, 3, 4], [0.52, 0.32, 0.12, 0.04])[0]
            choices = rng.choices(range(len(MENU)), item_weights(timestamp), k=number_of_lines)
            lines = []
            for line_number, item_number in enumerate(choices, 1):
                item_id, name, category, lunch, dinner = MENU[item_number]
                base = Decimal(dinner if timestamp.hour >= 17 else lunch)
                qty = rng.choices([1, 2, 3], [0.9, 0.09, 0.01])[0]
                mods = []
                if category in {"Rice Bowls", "Salad Bowls", "Signature Items"}:
                    if rng.random() < 0.13:
                        mods.append(
                            {
                                "id": "KS-EXTRA-TOPPING",
                                "name": "Extra topping",
                                "price": 0.25,
                                "quantity": 1,
                            }
                        )
                    if rng.random() < 0.09:
                        mods.append(
                            {
                                "id": "KS-EXTRA-SAUCE",
                                "name": "Extra sauce",
                                "price": 0.5,
                                "quantity": 1,
                            }
                        )
                    if rng.random() < 0.06:
                        double = 6 if "Bulgogi" in name else 5
                        mods.append(
                            {
                                "id": "KS-DOUBLE-PROTEIN",
                                "name": "Double protein",
                                "price": double,
                                "quantity": 1,
                            }
                        )
                upcharge = sum((Decimal(str(m["price"])) for m in mods), Decimal(0))
                lines.append(
                    (line_number, item_number, item_id, name, category, base, qty, upcharge, mods)
                )
            subtotal = sum((line[5] + line[7]) * line[6] for line in lines)
            for n, item_number, item_id, name, category, base, qty, upcharge, mods in lines:
                counters[source]["lines"] += 1
                counters[source]["quantity"] += qty
                if source == "doordash":
                    row = {
                        "business_id": "9900002",
                        "store_id": STORE_IDS[source],
                        "business_name": "K-Station Campus Scenario (SYNTHETIC)",
                        "store_name": STORE_NAME,
                        "dd_order_number": order_id,
                        "order_place_date": timestamp.date().isoformat(),
                        "order_place_time": timestamp.time().isoformat(),
                        "created_at": timestamp.replace(tzinfo=ZoneInfo(TIMEZONE))
                        .astimezone(UTC)
                        .isoformat()
                        .replace("+00:00", "Z"),
                        "timezone": TIMEZONE,
                        "dd_item_id": f"009902{item_number + 1:04d}",
                        "item_merchant_supplied_id": item_id,
                        "order_item_id": f"{order_id}-line-{n}",
                        "item_name": name,
                        "category_name": category,
                        "menu_name": "K-Station Inspired Synthetic Menu",
                        "order_item_quantity": qty,
                        "unit_price": money(base + upcharge),
                        "original_item_price": money(base),
                        "subtotal": money(subtotal),
                        "is_consumer_pickup": str(pickup),
                        "dashpass": str(serial % 4 != 0),
                        "mx_order_number": f"{serial:08d}" if pos_id else "",
                        "external_order_id": pos_id,
                    }
                else:
                    row = {
                        "grubhub_store_id": STORE_IDS[source],
                        "store_name": STORE_NAME,
                        "store_number": "001",
                        "external_id": "KS-SYN-TRUCK-001",
                        "order_number": order_id,
                        "order_uuid": str(uuid5(NAMESPACE, order_id)),
                        "partner_order_id": pos_id,
                        "order_date": timestamp.date().isoformat(),
                        "order_time_local": timestamp.time().isoformat(),
                        "order_time_zone": TIMEZONE,
                        "menu_item_id": item_id,
                        "menu_item_name": name,
                        "menu_item_category_name": category,
                        "menu_item_quantity": qty,
                        "menu_item_price": money(base),
                        "menu_item_modifiers": json.dumps(mods, separators=(",", ":")),
                        "fullfillment_type": "PICKUP" if pickup else "DELIVERY",
                    }
                writers[source].writerow(row)
    sources = {
        source: {
            **dict(counters[source]),
            "path": str(path.relative_to(output_dir)),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "store_ids": [STORE_IDS[source]],
            "columns": DD_HEADERS if source == "doordash" else GH_HEADERS,
        }
        for source, path in paths.items()
    }
    manifest = {
        "dataset": "kstation-october-2026-synthetic-v1",
        "is_synthetic": True,
        "seed": seed,
        "date_start": START.isoformat(),
        "date_end_inclusive": END.isoformat(),
        "timezone": TIMEZONE,
        "orders": len(scheduled),
        "sources": sources,
        "daily": daily,
        "day_types": DAY_TYPES,
        "location_mapping": {"KS-SYN-TRUCK-001": {"name": STORE_NAME, **STORE_IDS}},
        "menu": [
            {
                "canonical_synthetic_id": m[0],
                "doordash_item_id": f"009902{i + 1:04d}",
                "grubhub_item_id": m[0],
                "name": m[1],
                "category": m[2],
                "lunch_price_usd": m[3],
                "dinner_price_usd": m[4],
            }
            for i, m in enumerate(MENU)
        ],
        "source_attribution": {
            "menu_url": MENU_SOURCE,
            "hours_url": HOURS_SOURCE,
            "inspected_date": "2026-11-07",
            "menu_note": (
                "Campus PDF visually inspected; no publicly readable Grubhub menu obtained. "
                "Tartan Express is user-reported Grubhub name."
            ),
        },
        "designed_patterns": [
            "Recurring lunch12 and dinner18 rushes",
            "Thursday14 recurring smaller rush",
            "One isolated Oct21 15:00 spike",
            "Lunch favors rice bowls; dinner favors salad bowls",
            "Spicy BBQ Pork Belly Rice Bowl grows; Tangy Fried Chicken Rice Bowl declines",
        ],
        "assumptions": [
            "All orders and behavior are fabricated; actual platform participation is unverified.",
            "Clock-hour and day counts are merged across the two simulated feeds for one truck.",
            "Daily hours 11:00-16:00 and 17:00-20:30 are not verified historical October hours.",
            "Configured bowl names/IDs are synthetic choices, not verified provider products.",
            "Prices are public-menu-inspired USD assumptions, not verified October transactions.",
            "Lunch prices apply before 17:00. Dinner prices start 17:00; beef premium is in base.",
            (
                "Menu-inspired add-ons: topping $0.25, sauce $0.50, double protein $5 (beef $6). "
                "DD unit price includes these; GH records base price plus modifiers."
            ),
            "Complete orders include repeated dish lines and optional blank POS IDs; no refunds.",
            "No recipes, inventory, staffing, prep times, kitchen logs or external event evidence.",
            "October has 4-5 occurrences per weekday; no eight-week or accuracy claim is made.",
            "Different seeds reuse store IDs. Use distinct stores or databases for other variants.",
        ],
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20261107)
    args = parser.parse_args()
    try:
        manifest = generate(args.out, args.seed)
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Generation failed: {exc}\n")
    print(json.dumps({"orders": manifest["orders"], "sources": manifest["sources"]}, indent=2))


if __name__ == "__main__":
    main()
