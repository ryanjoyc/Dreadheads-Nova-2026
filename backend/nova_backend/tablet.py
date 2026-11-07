"""Sales-only K-Station tablet analysis; forecasts never read target/future sales.

The manifest explicitly pairs these synthetic platform stores and menu IDs.
No recipes, inventory, prep timing, or causal event explanations are inferred.
"""

import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

MANIFEST = Path(__file__).resolve().parents[2] / "data/kstation_demo/manifest.json"
if not MANIFEST.exists():
    MANIFEST = Path("/workspace/data/kstation_demo/manifest.json")
COHORT = {"doordash": "9900201", "grubhub": "8800201"}


def _label(slot):
    return f"{slot // 4:02d}:{slot % 4 * 15:02d}"


def _pages(fetch, params):
    cursors = set()
    while True:
        page = fetch(params)
        yield from page["data"]
        cursor = page["next_cursor"]
        if cursor is None:
            return
        if cursor in cursors:
            raise ValueError("Repeated cursor while reading sales")
        cursors.add(cursor)
        params = params.model_copy(update={"cursor": cursor})


def analyze_lines(lines, target: date, source=None, analysis=None):
    """Analyze normalized query rows, retaining provider identities until mapped."""
    if source not in (None, "doordash", "grubhub"):
        raise ValueError("Unknown sales source")
    manifest = json.loads(MANIFEST.read_text())
    menu = {item["canonical_synthetic_id"]: item for item in manifest["menu"]}
    mapping = {
        (provider, item[f"{provider}_item_id"]): item["canonical_synthetic_id"]
        for item in manifest["menu"]
        for provider in COHORT
    }
    by_day = defaultdict(list)
    seen_lines = set()
    for row in lines:
        provider = row["source"]
        if COHORT.get(provider) != row["external_store_id"] or (source and provider != source):
            continue
        if row.get("is_synthetic") is not True:
            raise ValueError("K-Station demo requires explicitly synthetic sales")
        line_key = str(row["id"])
        if line_key in seen_lines:
            raise ValueError("Duplicate sales line in analysis")
        seen_lines.add(line_key)
        item = mapping.get((provider, row["external_item_id"]))
        if item is None:
            raise ValueError("Unmapped K-Station item; update the explicit manifest mapping")
        placed = row["placed_at_local"]
        if isinstance(placed, str):
            placed = datetime.fromisoformat(placed)
        by_day[placed.date()].append(
            {
                "order": str(row["order_id"]),
                "item": item,
                "qty": Decimal(str(row["quantity"])),
                "slot": (placed.hour * 60 + placed.minute) // 15,
            }
        )

    history = sorted(
        day
        for day in by_day
        if target - timedelta(weeks=8) <= day < target and day.weekday() == target.weekday()
    )
    denominator = len(history)

    def traffic(rows):
        orders = [set() for _ in range(96)]
        for row in rows:
            orders[row["slot"]].add(row["order"])
        return [len(ids) for ids in orders]

    multipliers = [1.0] * 96
    if analysis is not None:
        for window in analysis["rush_hours"]:
            start = int(window["start"][:2]) * 4 + int(window["start"][3:]) // 15
            end = int(window["end"][:2]) * 4 + int(window["end"][3:]) // 15
            for slot in range(start, end):
                multipliers[slot] = window["multiplier"]

    def dishes(rows, divisor=1, start=0, end=96, projected=False):
        quantities = defaultdict(Decimal)
        for row in rows:
            if start <= row["slot"] < end:
                multiplier = Decimal(str(multipliers[row["slot"]])) if projected else Decimal(1)
                quantities[row["item"]] += row["qty"] * multiplier
        return [
            {
                "id": item_id,
                "name": menu[item_id]["name"],
                "category": menu[item_id]["category"],
                "quantity": round(float(quantity / divisor), 1),
            }
            for item_id, quantity in sorted(
                quantities.items(), key=lambda pair: (-pair[1], pair[0])
            )
        ]

    histories = [traffic(by_day[day]) for day in history]
    expected = [
        sum(values[slot] for values in histories) / denominator if denominator else 0.0
        for slot in range(96)
    ]
    active = [value for value in expected if value > 0]
    threshold = max(1.5 * sum(active) / len(active), 2.0) if active else 2.0
    history_rows = [row for day in history for row in by_day[day]]
    windows = []
    for slot, value in enumerate(expected):
        if value >= threshold:
            if windows and windows[-1][1] == slot:
                windows[-1][1] = slot + 1
            else:
                windows.append([slot, slot + 1])
    metadata = {}
    if analysis is not None:
        windows = []
        for window in analysis["rush_hours"]:
            start = int(window["start"][:2]) * 4 + int(window["start"][3:]) // 15
            end = int(window["end"][:2]) * 4 + int(window["end"][3:]) // 15
            windows.append((start, end))
            metadata[(start, end)] = window
        expected = [value * multipliers[slot] for slot, value in enumerate(expected)]
        threshold = analysis["rush_threshold"]
    rush_slots = {slot for start, end in windows for slot in range(start, end)}
    rushes = []
    for start, end in windows:
        peak = max(range(start, end), key=expected.__getitem__)
        rushes.append(
            {
                "start": _label(start),
                "end": _label(end),
                "expected_orders": round(sum(expected[start:end]), 1),
                "peak_at": _label(peak),
                "peak_orders": round(expected[peak], 1),
                "dishes": dishes(history_rows, denominator, start, end, projected=True),
                **{
                    key: value
                    for key, value in metadata.get((start, end), {}).items()
                    if key in {"reason", "confidence", "consistency", "intensity", "multiplier"}
                },
                **({"confidence": "low"} if analysis is not None and denominator < 3 else {}),
            }
        )
    peak = max(range(96), key=expected.__getitem__) if any(expected) else None
    observed_rows = by_day.get(target)
    observed_traffic = traffic(observed_rows) if observed_rows else None
    reason = (
        f"Average of {denominator} earlier {target.strftime('%A')}s, using 15-minute slots."
        if denominator
        else "No earlier matching weekdays are available; no forecast is inferred."
    )
    return {
        "dataset": "kstation",
        "restaurant": "Tartan Express / K-Station (synthetic)",
        "date": target.isoformat(),
        "source": source or "all",
        "is_synthetic": True,
        "method": analysis["method"] if analysis is not None else "same_weekday_average",
        "analysis": {
            key: analysis[key] for key in ["method", "model", "summary", "flags", "agent_trace"]
        }
        if analysis is not None
        else None,
        "history_dates": [day.isoformat() for day in history],
        "history_days": denominator,
        "reason": reason,
        "forecast": {
            "orders": round(sum(expected), 1),
            "peak_at": _label(peak) if peak is not None else None,
            "peak_orders": round(expected[peak], 1) if peak is not None else 0,
            "threshold": round(threshold, 2),
            "rushes": rushes,
            "slots": [
                {
                    "time": _label(slot),
                    "expected_orders": round(value, 2),
                    "is_rush": slot in rush_slots,
                }
                for slot, value in enumerate(expected)
            ],
            "dishes": dishes(history_rows, denominator, projected=True) if denominator else [],
        },
        "observed": {
            "orders": len({row["order"] for row in observed_rows}),
            "slots": [
                {"time": _label(slot), "orders": count}
                for slot, count in enumerate(observed_traffic)
            ],
            "dishes": dishes(observed_rows),
        }
        if observed_rows
        else None,
        "historical_days": [
            {
                "date": day.isoformat(),
                "orders": len({row["order"] for row in rows}),
                "peak_at": _label(max(range(96), key=traffic(rows).__getitem__)),
                "peak_orders": max(traffic(rows)),
            }
            for day, rows in sorted(by_day.items())
        ],
        "caveat": "Fabricated sales demonstrate the pipeline, not forecast accuracy. "
        "Only earlier same weekdays with recorded sales enter the average; missing days "
        "are not assumed closed. Dish quantities are expected sales, "
        "not ingredient or prep instructions.",
    }


def _cohort_lines(session, source=None):
    """Read only the explicitly mapped K-Station cohort through shared sales queries."""
    from nova_backend import queries
    from nova_backend.schemas import SaleParams, StoreParams

    stores = [
        row
        for row in _pages(
            lambda params: queries.list_stores(session, params),
            StoreParams(source=source, limit=500),
        )
        if COHORT.get(row["source"]) == row["external_store_id"]
        and (source is None or row["source"] == source)
    ]
    required_sources = {source} if source else set(COHORT)
    if {store["source"] for store in stores} != required_sources:
        raise ValueError("Import the K-Station demo CSVs before loading the tablet")
    lines = []
    for store in stores:
        params = SaleParams(store_id=store["id"], source=store["source"], limit=500)
        lines.extend(_pages(lambda params: queries.list_order_lines(session, params), params))
    if not lines:
        raise ValueError("K-Station stores have no sales; import the demo CSVs")
    return lines


def tablet_analysis(session, target: date, source=None, use_agent=False, context=None):
    """Bind John's rush engine to the explicit cohort, then adapt dish/window results."""
    from nova_backend.rush_agent import predict_rush_hours
    from nova_backend.schemas import RushParams
    from nova_backend.tablet_tools import TabletTools

    lines = _cohort_lines(session, source)
    # Validate the complete input before allowing model tools to inspect it.
    analyze_lines(lines, target, source)
    params = RushParams(
        date=target,
        source=source,
        use_agent=use_agent,
        context=context,
        store_name="Tartan Express - K-Station (SYNTHETIC)",
    )
    tools = TabletTools(lines, params)
    actual = defaultdict(set)
    for row in lines:
        placed = row["placed_at_local"]
        if placed.date() == target:
            minute = (placed.hour * 60 + placed.minute) // 15 * 15
            actual[minute].add(row["order_id"])
    analysis = predict_rush_hours(
        session,
        params,
        forecast=tools.fc,
        actual_traffic={minute: len(orders) for minute, orders in actual.items()},
        bound_tools=tools,
    )
    return analyze_lines(lines, target, source, analysis)


def analyze_outlook(lines, target: date, source=None, days=7):
    """Project a span from information available strictly before its first day.

    Later dates in the span cannot use observed sales from earlier dates in the
    span. Each forecast uses its weekday's available history without recursion.
    """
    if not isinstance(days, int) or isinstance(days, bool) or not 1 <= days <= 31:
        raise ValueError("Outlook days must be between 1 and 31")
    history = []
    for row in lines:
        placed = row["placed_at_local"]
        if isinstance(placed, str):
            placed = datetime.fromisoformat(placed)
        if placed.date() < target:
            history.append(row)
    summaries = []
    dish_totals = {}
    for offset in range(days):
        day = target + timedelta(days=offset)
        result = analyze_lines(history, day, source)
        summaries.append(
            {
                "date": day.isoformat(),
                "expected_orders": result["forecast"]["orders"],
                "history_days": result["history_days"],
            }
        )
        for item in result["forecast"]["dishes"]:
            total = dish_totals.setdefault(
                item["id"],
                {
                    "id": item["id"],
                    "name": item["name"],
                    "category": item["category"],
                    "quantity": Decimal(0),
                },
            )
            total["quantity"] += Decimal(str(item["quantity"]))
    dishes = [
        {**item, "quantity": round(float(item["quantity"]), 1)}
        for item in sorted(dish_totals.values(), key=lambda item: (-item["quantity"], item["id"]))
    ]
    return {
        "date": target.isoformat(),
        "source": source or "all",
        "days": summaries,
        "dishes": dishes,
        "caveat": "Synthetic sales outlook, not a pile to cook now. Each day uses only "
        "recorded same weekdays before the outlook start; days without matching history "
        "have no inferred demand. Totals sum daily expected sales, not ingredient or prep needs.",
    }


def tablet_outlook(session, target: date, source=None, days=7):
    """Load the mapped sales cohort once for the whole outlook span."""
    return analyze_outlook(_cohort_lines(session, source), target, source, days)
