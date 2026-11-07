"""Request-local agent tools over the explicitly selected synthetic sales cohort.

The model can inspect historical counts but cannot change its store scope or see
the target day. No tool calls the database or a remote API.
"""

import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal

from nova_backend import analytics, rush
from nova_backend.rush_agent import Tools
from nova_backend.tablet import COHORT, MANIFEST


class TabletTools(Tools):
    """The rush agent's existing tool contract, served from one bounded snapshot."""

    def __init__(self, lines, params, fc=None):
        super().__init__(None, params, params.scope())
        manifest = json.loads(MANIFEST.read_text())
        mapping = {
            (provider, item[f"{provider}_item_id"]): item
            for item in manifest["menu"]
            for provider in COHORT
        }
        self.rows = []
        for line in lines:
            provider = line["source"]
            if COHORT.get(provider) != line["external_store_id"]:
                raise ValueError("Agent tools require the explicit K-Station store cohort")
            if line.get("is_synthetic") is not True:
                raise ValueError("Agent tools require explicitly synthetic sales")
            if params.source and provider != params.source:
                continue
            if params.store_id and str(line["store_id"]) != str(params.store_id):
                continue
            if params.store_name:
                # K-Station is the one explicitly mapped synthetic truck. A
                # different requested name must never broaden the cohort.
                if params.store_name.casefold() not in (
                    "tartan express - k-station (synthetic)".casefold()
                ):
                    continue
            placed = line["placed_at_local"]
            if isinstance(placed, str):
                placed = datetime.fromisoformat(placed)
            if placed.date() >= params.on_date:
                continue
            item = mapping.get((provider, line["external_item_id"]))
            if item is None:
                raise ValueError("Unmapped K-Station menu item in agent snapshot")
            self.rows.append(
                {
                    "placed": placed,
                    "order": (provider, line["external_store_id"], str(line["order_id"])),
                    "item_id": item["canonical_synthetic_id"],
                    "item_name": item["name"],
                    "quantity": Decimal(str(line["quantity"])),
                }
            )
        self.fc = fc or self.forecast()

    def _traffic(self, day):
        orders = defaultdict(set)
        for row in self.rows:
            placed = row["placed"]
            if placed.date() == day:
                minute = placed.hour * 60 + placed.minute
                slot = minute - minute % self.params.slot_minutes
                orders[slot].add(row["order"])
        return {slot: len(ids) for slot, ids in orders.items()}

    def forecast(self, weeks=None):
        """Build the Python forecast from historical rows in this request only."""
        weeks = int(self.params.weeks if weeks is None else weeks)
        if not 1 <= weeks <= 26:
            raise ValueError("weeks must be 1-26")
        history = {}
        for back in range(1, weeks + 1):
            day = self.params.on_date - timedelta(weeks=back)
            counts = self._traffic(day)
            if counts:
                history[day] = counts
        return rush.forecast_from_history(self.params.on_date, self.params.slot_minutes, history)

    def get_rush_forecast(self, args):
        fc = self.forecast(args.get("weeks"))
        return {
            "history_days": [day.isoformat() for day in fc.history],
            "typical_orders_per_slot": round(fc.typical, 2),
            "rush_threshold": round(fc.threshold, 2),
            "expected_by_slot": {
                rush.label(slot): round(value, 2) for slot, value in fc.expected.items()
            },
            "rush_windows": [fc.window_stats(start, end) for start, end in fc.rush_windows()],
        }

    def get_day_traffic(self, args):
        day = date.fromisoformat(args["date"])
        if day >= self.params.on_date:
            raise ValueError("Only days before the day being predicted are available")
        return {"date": day.isoformat(), "weekday": day.strftime("%A")} | rush.day_spikes(
            self._traffic(day), self.params.slot_minutes
        )

    def _matching_rows(self, args):
        start, end = self._past_range(args)
        time_start = self._clock(args, "time_start")
        time_end = self._clock(args, "time_end")
        if time_start is not None and time_start == time_end:
            raise ValueError("time_start and time_end must differ")
        return (
            start,
            end,
            [
                row
                for row in self.rows
                if start <= row["placed"].date() < end
                and analytics._in_time_window(row["placed"], time_start, time_end)
            ],
        )

    def count_orders(self, args):
        start, end, rows = self._matching_rows(args)
        wanted = (args.get("item_name") or "").casefold()
        orders = {row["order"] for row in rows if wanted in row["item_name"].casefold()}
        return {"orders": len(orders), "days": (end - start).days}

    def get_top_dishes(self, args):
        _start, _end, rows = self._matching_rows(args)
        limit = int(args.get("limit", 5))
        if not 1 <= limit <= 20:
            raise ValueError("limit must be 1-20")
        units = defaultdict(Decimal)
        orders = defaultdict(set)
        names = {}
        for row in rows:
            item = row["item_id"]
            units[item] += row["quantity"]
            orders[item].add(row["order"])
            names[item] = row["item_name"]
        ranked = sorted(units, key=lambda item: (-units[item], -len(orders[item]), names[item]))
        return {
            "dishes": [
                {"item_name": names[item], "units": float(units[item]), "orders": len(orders[item])}
                for item in ranked[:limit]
            ]
        }
