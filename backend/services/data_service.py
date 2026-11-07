"""
Plain-Python data layer.

Loads the synthetic CSVs, merges DoorDash and Grubhub into one order_lines table,
and does all of the counting and math from handoffs/recommendations-spec.md.
The LLM never computes quantities: it reads these results through tools and only
chooses bounded multipliers (0.5x-2.0x) with reasons.
"""

from __future__ import annotations

import json
import math
import os
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(
    os.getenv("DATA_DIR", REPO_ROOT / "data" / "nova_sample_data" / "nova_sample_data" / "data")
)

SLOT_MINUTES = 15
BASELINE_WEEKS = 8
MULT_MIN, MULT_MAX = 0.5, 2.0
DEFAULT_BUFFER = 0.10

# Minute-of-day boundaries. "lunch" includes the morning (breakfast burritos).
DAYPARTS = {
    "lunch": (0, 14 * 60),
    "afternoon": (14 * 60, 17 * 60),
    "dinner": (17 * 60, 21 * 60),
    "late": (21 * 60, 24 * 60),
}
DAYPART_NAMES = list(DAYPARTS)
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def clamp_multiplier(value: Any) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 1.0
    if math.isnan(v):
        return 1.0
    return max(MULT_MIN, min(MULT_MAX, v))


def slot_label(slot: int) -> str:
    minutes = (slot * SLOT_MINUTES) % (24 * 60)
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def minute_label(minute: int) -> str:
    minute = max(0, minute)
    return f"{minute // 60:02d}:{minute % 60:02d}"


def daypart_of_slot(slot: int) -> str:
    minute = slot * SLOT_MINUTES
    for name, (start, end) in DAYPARTS.items():
        if start <= minute < end:
            return name
    return "late"


def _r(x: float, nd: int = 1) -> float:
    return round(float(x), nd)


class DataStore:
    """Loads everything once; all methods are read-only."""

    def __init__(self, data_dir: Path = DATA_DIR):
        ref = Path(data_dir) / "reference"
        plat = Path(data_dir) / "platform_reports"
        ops = Path(data_dir) / "operations"

        # ---- reference tables -------------------------------------------------
        self.locations = pd.read_csv(ref / "locations.csv", dtype=str)
        self.location_keys = list(self.locations.location_key)
        self.location_hours = {
            row.location_key: {int(k): v for k, v in json.loads(row.hours_by_weekday).items()}
            for row in self.locations.itertuples()
        }
        self.menu = pd.read_csv(ref / "menu_items.csv", dtype={"menu_item_id": str})
        self.menu_names = dict(zip(self.menu.menu_item_id, self.menu.menu_item_name))
        self.components = pd.read_csv(ref / "prep_components.csv", dtype={"component_id": str})
        self.comp = self.components.set_index("component_id")
        self.recipes = pd.read_csv(
            ref / "recipes.csv", dtype={"menu_item_id": str, "component_id": str}
        )
        modifiers = pd.read_csv(ref / "modifiers.csv", dtype=str)
        self.modifier_adjustments = {
            row.modifier_id: json.loads(row.component_adjustments or "[]")
            for row in modifiers.itertuples()
        }

        ctx = pd.read_csv(ref / "daily_context.csv", dtype=str, keep_default_na=False)
        self.context: Dict[str, Dict[str, Any]] = {}
        for row in ctx.to_dict("records"):
            self.context[row["date"]] = {
                "date": row["date"],
                "weekday": row["weekday"],
                "high_temp_f": float(row["high_temp_f"]) if row["high_temp_f"] else None,
                "precip_in": float(row["precip_in"]) if row["precip_in"] else None,
                "weather": row["weather"] or None,
                "university_in_session": row["university_in_session"] == "True",
                "holiday": row["holiday"] or None,
                "local_event": row["local_event"] or None,
            }

        self.prep_log = pd.read_csv(
            ops / "daily_prep_log.csv",
            dtype={"location_key": str, "date": str, "component_id": str, "ran_out_hour_local": str},
        )

        # ---- platform reports -> one order_lines table ------------------------
        self.lines = self._load_order_lines(plat)
        self.first_date = date.fromisoformat(self.lines.date.min())
        self.last_date = date.fromisoformat(self.lines.date.max())

        g = self.lines.groupby
        self.daily_orders = g(["location", "date"]).order_id.nunique()
        self.daypart_orders = g(["location", "date", "daypart"]).order_id.nunique()
        self.slot_orders = (
            g(["location", "date", "slot"]).order_id.nunique().rename("orders").reset_index()
        )
        self.item_slot_qty = g(["location", "date", "item_id", "slot"]).qty.sum().reset_index()
        delivery = self.lines.drop_duplicates("order_id")
        self.daypart_delivery = (
            delivery.assign(is_delivery=delivery.fulfillment == "delivery")
            .groupby(["location", "date", "daypart"])
            .is_delivery.agg(["sum", "count"])
        )

        self.per_unit = self._build_per_unit_components()

    # ------------------------------------------------------------------ loading
    def _load_order_lines(self, plat: Path) -> pd.DataFrame:
        dd = pd.read_csv(plat / "doordash_order_detail.csv", dtype=str, keep_default_na=False)
        gh = pd.read_csv(plat / "grubhub_menu_line_items.csv", dtype=str, keep_default_na=False)
        dd_loc = dict(zip(self.locations.doordash_store_id, self.locations.location_key))
        gh_loc = dict(zip(self.locations.grubhub_store_id, self.locations.location_key))

        dd_lines = pd.DataFrame(
            {
                "source": "doordash",
                "location": dd.store_id.map(dd_loc),
                "order_id": "dd-" + dd.dd_order_number,
                "date": dd.order_place_date,
                "time": dd.order_place_time,
                "item_id": dd.item_merchant_supplied_id,
                "qty": dd.order_item_quantity.astype(int),
                "fulfillment": dd.is_consumer_pickup.map({"True": "pickup", "False": "delivery"}),
                "modifiers": "[]",
            }
        )
        gh_lines = pd.DataFrame(
            {
                "source": "grubhub",
                "location": gh.grubhub_store_id.map(gh_loc),
                "order_id": "gh-" + gh.order_number,
                "date": gh.order_date,
                "time": gh.order_time_local,
                "item_id": gh.menu_item_id,
                "qty": gh.menu_item_quantity.astype(int),
                "fulfillment": gh.fullfillment_type.str.lower(),
                "modifiers": gh.menu_item_modifiers.replace("", "[]"),
            }
        )
        lines = pd.concat([dd_lines, gh_lines], ignore_index=True)
        lines = lines[lines.location.notna()].copy()
        hm = lines.time.str.split(":", expand=True)
        lines["minute"] = hm[0].astype(int) * 60 + hm[1].astype(int)
        lines["slot"] = lines.minute // SLOT_MINUTES
        lines["daypart"] = lines.slot.map(daypart_of_slot)
        return lines

    def _build_per_unit_components(self) -> pd.DataFrame:
        """Component qty per menu item = recipe qty + expected modifier adjustment.

        The modifier part is estimated from Grubhub only (DoorDash exports have no
        modifier column), so it is kept in its own column and labeled downstream.
        """
        gh = self.lines[(self.lines.source == "grubhub") & (self.lines.modifiers != "[]")]
        extra: Dict[tuple, float] = {}
        for item_id, line_qty, mods in zip(gh.item_id, gh.qty, gh.modifiers):
            for mod in json.loads(mods):
                for adj in self.modifier_adjustments.get(mod.get("id"), []):
                    key = (item_id, adj["component_id"])
                    extra[key] = extra.get(key, 0.0) + adj["qty"] * mod.get("quantity", 1) * line_qty
        gh_item_qty = self.lines[self.lines.source == "grubhub"].groupby("item_id").qty.sum()

        per_unit = self.recipes.rename(columns={"qty_per_item": "recipe_qty"}).copy()
        per_unit["modifier_qty"] = 0.0
        for (item_id, comp_id), total in extra.items():
            rate = total / gh_item_qty.get(item_id, 1)
            mask = (per_unit.menu_item_id == item_id) & (per_unit.component_id == comp_id)
            if mask.any():
                per_unit.loc[mask, "modifier_qty"] += rate
            else:
                per_unit.loc[len(per_unit)] = [item_id, comp_id, 0.0, rate]
        return per_unit.rename(columns={"menu_item_id": "item_id"})

    # ------------------------------------------------------------------ context
    def get_context(self, date_str: str, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        d = date.fromisoformat(date_str)
        base = self.context.get(date_str)
        ctx = dict(base) if base else {
            "date": date_str,
            "weekday": WEEKDAYS[d.weekday()],
            "high_temp_f": None,
            "precip_in": None,
            "weather": None,
            "university_in_session": None,
            "holiday": None,
            "local_event": None,
        }
        ctx["in_calendar"] = base is not None
        if overrides:
            ctx.update({k: v for k, v in overrides.items() if v is not None})
            ctx["manager_supplied"] = sorted(k for k, v in overrides.items() if v is not None)
        return ctx

    def is_special(self, date_str: str) -> bool:
        c = self.context.get(date_str)
        return bool(c and (c["holiday"] or c["local_event"]))

    def special_day_labels(self) -> Dict[str, List[str]]:
        holidays = sorted({c["holiday"] for c in self.context.values() if c["holiday"]})
        events = sorted({c["local_event"] for c in self.context.values() if c["local_event"]})
        return {"holidays": holidays, "local_events": events}

    def has_data(self, location: str, date_str: str) -> bool:
        return (location, date_str) in self.daily_orders.index

    # ------------------------------------------------------------------ baseline
    def baseline_days(self, location: str, target: str) -> List[str]:
        """Last 8 same weekdays before target that have data and aren't special days."""
        d = date.fromisoformat(target) - timedelta(days=7)
        days: List[str] = []
        while d >= self.first_date and len(days) < BASELINE_WEEKS:
            ds = d.isoformat()
            if d <= self.last_date and self.has_data(location, ds) and not self.is_special(ds):
                days.append(ds)
            d -= timedelta(days=7)
        return days

    def _baseline_orders(self, location: str, days: List[str]) -> Dict[str, Any]:
        if not days:
            return {"daily": 0.0, "dayparts": {dp: 0.0 for dp in DAYPART_NAMES}}
        n = len(days)
        daily = sum(self.daily_orders.get((location, d), 0) for d in days) / n
        dps = {
            dp: sum(self.daypart_orders.get((location, d, dp), 0) for d in days) / n
            for dp in DAYPART_NAMES
        }
        return {"daily": daily, "dayparts": dps}

    def baseline_summary(self, location: str, target: str) -> Dict[str, Any]:
        days = self.baseline_days(location, target)
        orders = self._baseline_orders(location, days)
        n = max(len(days), 1)

        items = self.item_slot_qty[
            (self.item_slot_qty.location == location) & self.item_slot_qty.date.isin(days)
        ].copy()
        items["daypart"] = items.slot.map(daypart_of_slot)
        by_dp = items.groupby(["daypart", "item_id"]).qty.sum() / n
        top_items = {}
        for dp in DAYPART_NAMES:
            if dp in by_dp.index.get_level_values(0):
                s = by_dp.loc[dp].sort_values(ascending=False).head(5)
                top_items[dp] = [
                    {"item": self.menu_names.get(i, i), "item_id": i, "avg_qty": _r(q)}
                    for i, q in s.items()
                ]

        delivery_share = {}
        for dp in DAYPART_NAMES:
            num = sum(self.daypart_delivery["sum"].get((location, d, dp), 0) for d in days)
            den = sum(self.daypart_delivery["count"].get((location, d, dp), 0) for d in days)
            delivery_share[dp] = _r(num / den, 2) if den else None

        return {
            "location": location,
            "target_date": target,
            "method": f"average of the last {BASELINE_WEEKS} same weekdays, holidays and events excluded",
            "baseline_days": [
                {
                    "date": d,
                    "orders": int(self.daily_orders.get((location, d), 0)),
                    "weather": self.context.get(d, {}).get("weather"),
                    "university_in_session": self.context.get(d, {}).get("university_in_session"),
                }
                for d in days
            ],
            "avg_daily_orders": _r(orders["daily"]),
            "avg_orders_by_daypart": {k: _r(v) for k, v in orders["dayparts"].items()},
            "delivery_share_by_daypart": delivery_share,
            "top_items_by_daypart": top_items,
        }

    # ------------------------------------------------------------------ evidence
    def find_similar_days(
        self,
        location: str,
        before_date: str,
        holiday: Optional[str] = None,
        local_event: Optional[str] = None,
        weather: Optional[str] = None,
        university_in_session: Optional[bool] = None,
        weekday: Optional[str] = None,
        limit: int = 6,
    ) -> Dict[str, Any]:
        """Past days matching the filters, each compared to its own baseline."""
        before = date.fromisoformat(before_date)
        matches = []
        for ds in sorted(self.context, reverse=True):
            c = self.context[ds]
            if date.fromisoformat(ds) >= before or not self.has_data(location, ds):
                continue
            if holiday and not (c["holiday"] and holiday.lower() in c["holiday"].lower()):
                continue
            if local_event and not (c["local_event"] and local_event.lower() in c["local_event"].lower()):
                continue
            if weather and c["weather"] != weather.lower():
                continue
            if university_in_session is not None and c["university_in_session"] != university_in_session:
                continue
            if weekday and c["weekday"].lower() != weekday.lower():
                continue

            base = self._baseline_orders(location, self.baseline_days(location, ds))
            actual = int(self.daily_orders.get((location, ds), 0))
            dp_ratio = {}
            for dp in DAYPART_NAMES:
                b = base["dayparts"][dp]
                a = self.daypart_orders.get((location, ds, dp), 0)
                dp_ratio[dp] = _r(a / b, 2) if b >= 3 else None
            matches.append(
                {
                    "date": ds,
                    "weekday": c["weekday"],
                    "weather": c["weather"],
                    "holiday": c["holiday"],
                    "local_event": c["local_event"],
                    "university_in_session": c["university_in_session"],
                    "actual_orders": actual,
                    "baseline_orders": _r(base["daily"]),
                    "ratio_vs_baseline": _r(actual / base["daily"], 2) if base["daily"] else None,
                    "daypart_ratio_vs_baseline": dp_ratio,
                }
            )
            if len(matches) >= limit:
                break

        ratios = [m["ratio_vs_baseline"] for m in matches if m["ratio_vs_baseline"]]
        return {
            "location": location,
            "filters": {
                k: v
                for k, v in {
                    "holiday": holiday,
                    "local_event": local_event,
                    "weather": weather,
                    "university_in_session": university_in_session,
                    "weekday": weekday,
                }.items()
                if v is not None
            },
            "count": len(matches),
            "mean_ratio_vs_baseline": _r(sum(ratios) / len(ratios), 2) if ratios else None,
            "days": matches,
        }

    def stockout_history(self, location: str, target: str, weeks: int = BASELINE_WEEKS) -> Dict[str, Any]:
        """Run-outs on recent same weekdays, from the kitchen prep log."""
        t = date.fromisoformat(target)
        log = self.prep_log[self.prep_log.location_key == location]
        dates = sorted(
            {d for d in log.date.unique() if date.fromisoformat(d) < t
             and date.fromisoformat(d).weekday() == t.weekday()},
            reverse=True,
        )[:weeks]
        rows = log[log.date.isin(dates) & log.ran_out_hour_local.notna()]
        events = [
            {
                "date": r.date,
                "component_id": r.component_id,
                "component": r.component_name,
                "ran_out_at": r.ran_out_hour_local,
                "unmet_qty": _r(r.qty_demand_unmet),
                "unit": r.unit,
            }
            for r in rows.sort_values(["component_id", "date"]).itertuples()
        ]
        counts: Dict[str, int] = {}
        for e in events:
            counts[e["component"]] = counts.get(e["component"], 0) + 1
        return {
            "location": location,
            "weekday": WEEKDAYS[t.weekday()],
            "days_checked": dates,
            "runout_counts": dict(sorted(counts.items(), key=lambda kv: -kv[1])),
            "events": events,
            "note": "Sales on run-out days understate true demand.",
        }

    # ------------------------------------------------------------------ forecast + plan
    def forecast_item_slots(
        self,
        location: str,
        target: str,
        daypart_multipliers: Optional[Dict[str, float]] = None,
    ) -> pd.DataFrame:
        days = self.baseline_days(location, target)
        n = max(len(days), 1)
        fc = (
            self.item_slot_qty[
                (self.item_slot_qty.location == location) & self.item_slot_qty.date.isin(days)
            ]
            .groupby(["item_id", "slot"])
            .qty.sum()
            .div(n)
            .rename("qty_base")
            .reset_index()
        )
        fc["daypart"] = fc.slot.map(daypart_of_slot)
        mult = {dp: clamp_multiplier((daypart_multipliers or {}).get(dp, 1.0)) for dp in DAYPART_NAMES}
        fc["qty"] = fc.qty_base * fc.daypart.map(mult)
        return fc

    def forecast_slot_orders(self, location: str, target: str, daypart_multipliers=None) -> pd.Series:
        days = self.baseline_days(location, target)
        n = max(len(days), 1)
        so = self.slot_orders[(self.slot_orders.location == location) & self.slot_orders.date.isin(days)]
        s = so.groupby("slot").orders.sum() / n
        mult = {dp: clamp_multiplier((daypart_multipliers or {}).get(dp, 1.0)) for dp in DAYPART_NAMES}
        return s * s.index.map(lambda sl: mult[daypart_of_slot(sl)])

    def prep_plan(
        self,
        location: str,
        target: str,
        daypart_multipliers: Optional[Dict[str, float]] = None,
        component_multipliers: Optional[Dict[str, float]] = None,
        buffer: float = DEFAULT_BUFFER,
        on_hand: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        """Feature 1 (prep sheet) + Feature 2 (timeline). Pure math, no LLM."""
        on_hand = on_hand or {}
        comp_mult = {k: clamp_multiplier(v) for k, v in (component_multipliers or {}).items()}
        fc = self.forecast_item_slots(location, target, daypart_multipliers)
        m = fc.merge(self.per_unit, on="item_id")
        m["cmult"] = m.component_id.map(comp_mult).fillna(1.0)
        m["need"] = m.qty * (m.recipe_qty + m.modifier_qty) * m.cmult
        m["need_base"] = m.qty_base * (m.recipe_qty + m.modifier_qty)
        m["need_modifier"] = m.qty * m.modifier_qty * m.cmult
        comp_slot = m.groupby(["component_id", "slot"]).need.sum()

        weekday = date.fromisoformat(target).weekday()
        open_h, close_h = self.location_hours[location][weekday]
        open_min, close_min = int(open_h * 60), int(close_h * 60)

        rows, timeline = [], []
        for comp_id, info in self.comp.iterrows():
            sub = m[m.component_id == comp_id]
            if sub.empty:
                continue
            need = float(sub.need.sum()) * (1 + buffer)
            have = float(on_hand.get(comp_id, 0.0))
            to_prep = max(0.0, need - have)
            batch = float(info.batch_yield)
            batches = math.ceil(to_prep / batch - 1e-9) if to_prep > 0 else 0
            by_dp = (sub.groupby("daypart").need.sum() * (1 + buffer)).to_dict()
            rows.append(
                {
                    "component_id": comp_id,
                    "ingredient": info.component_name,
                    "unit": info.unit,
                    "baseline_need": _r(sub.need_base.sum()),
                    "need": _r(need),
                    "need_by_daypart": {dp: _r(by_dp.get(dp, 0.0)) for dp in DAYPART_NAMES},
                    "modifier_estimate": _r(sub.need_modifier.sum() * (1 + buffer)),
                    "on_hand": _r(have),
                    "to_prep": _r(batches * batch),
                    "batches": batches,
                    "batch_yield": batch,
                    "prep_minutes_per_batch": int(info.prep_minutes_per_batch),
                    "hold_hours": float(info.hold_hours),
                    "est_cost_usd": _r(batches * batch * float(info.unit_cost_usd), 2),
                    "supplier_lead_days": int(info.supplier_lead_days),
                    "component_multiplier": comp_mult.get(comp_id, 1.0),
                }
            )
            timeline += self._batch_schedule(
                comp_id, info, comp_slot.loc[comp_id] * (1 + buffer), have, batches, open_min, close_min
            )

        rows.sort(key=lambda r: (-r["hold_hours"], r["ingredient"]))
        timeline += self._peak_windows(location, target, daypart_multipliers)
        timeline.sort(key=lambda e: (e["minute"], e.get("ingredient") or ""))
        return {
            "location": location,
            "date": target,
            "baseline_days": self.baseline_days(location, target),
            "buffer": buffer,
            "daypart_multipliers": {
                dp: clamp_multiplier((daypart_multipliers or {}).get(dp, 1.0)) for dp in DAYPART_NAMES
            },
            "open": minute_label(open_min),
            "close": minute_label(close_min),
            "prep_sheet": rows,
            "timeline": timeline,
        }

    def _batch_schedule(self, comp_id, info, slot_need: pd.Series, have, batches, open_min, close_min):
        events = []
        cum = slot_need.sort_index().cumsum()
        batch = float(info.batch_yield)
        prep_min = int(info.prep_minutes_per_batch)
        hold_min = float(info.hold_hours) * 60
        for k in range(1, batches + 1):
            threshold = have + (k - 1) * batch
            needed = cum[cum > threshold]
            if needed.empty:
                break
            ready_min = max(int(needed.index[0]) * SLOT_MINUTES, open_min)
            start_min = ready_min - prep_min
            used_up = cum[cum > threshold + batch]
            last_use_min = int(used_up.index[0]) * SLOT_MINUTES if not used_up.empty else close_min
            reason = f"Needed by {minute_label(ready_min)}; {prep_min} min prep"
            if k == 1 and ready_min <= open_min:
                reason = f"Needed at open ({minute_label(open_min)}); {prep_min} min prep"
            if last_use_min - ready_min > hold_min:
                reason += f". Lasts past its {info.hold_hours:g} h hold; consider a half batch"
            events.append(
                {
                    "minute": start_min,
                    "time": minute_label(start_min),
                    "action": f"Start batch {k} of {info.component_name}",
                    "ingredient": info.component_name,
                    "component_id": comp_id,
                    "kind": "batch",
                    "before_open": start_min < open_min,
                    "reason": reason,
                }
            )
        return events

    def _peak_windows(self, location, target, daypart_multipliers):
        orders = self.forecast_slot_orders(location, target, daypart_multipliers)
        if orders.empty:
            return []
        total = orders.sum()
        events = []
        for dp, (a, b) in DAYPARTS.items():
            s = orders[(orders.index * SLOT_MINUTES >= a) & (orders.index * SLOT_MINUTES < b)]
            if s.sum() < 0.08 * total or len(s) < 4:
                continue
            window = s.rolling(4).sum()
            end_slot = int(window.idxmax())
            start_slot = end_slot - 3
            share = window.max() / s.sum()
            events.append(
                {
                    "minute": start_slot * SLOT_MINUTES,
                    "time": slot_label(start_slot),
                    "end": slot_label(end_slot + 1),
                    "action": f"Peak {dp} hour {slot_label(start_slot)}-{slot_label(end_slot + 1)}",
                    "ingredient": None,
                    "kind": "peak",
                    "reason": f"~{window.max():.0f} orders, {share:.0%} of {dp} volume",
                }
            )
        return events

    # ------------------------------------------------------------------ backtest
    def backtest(self, location: str, target: str, plan: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """If the target date is in history, compare our plan to the manager's actual prep."""
        log = self.prep_log[(self.prep_log.location_key == location) & (self.prep_log.date == target)]
        if log.empty:
            return None
        ours = {r["component_id"]: r["to_prep"] + r["on_hand"] for r in plan["prep_sheet"]}
        rows = []
        tot = {"ours_leftover": 0.0, "manager_leftover": 0.0}
        ours_out, mgr_out = [], []
        for r in log.itertuples():
            demand = float(r.qty_used + r.qty_demand_unmet)
            cost = float(self.comp.loc[r.component_id].unit_cost_usd)
            mine = ours.get(r.component_id, 0.0)
            mgr = float(r.opening_on_hand + r.qty_prepped)
            ol, ml = max(0.0, mine - demand) * cost, max(0.0, mgr - demand) * cost
            tot["ours_leftover"] += ol
            tot["manager_leftover"] += ml
            if mine < demand - 1e-6:
                ours_out.append(r.component_name)
            if mgr < demand - 1e-6:
                mgr_out.append(r.component_name)
            rows.append(
                {
                    "component": r.component_name,
                    "true_demand": _r(demand),
                    "ours": _r(mine),
                    "manager": _r(mgr),
                    "unit": r.unit,
                }
            )
        actual_orders = int(self.daily_orders.get((location, target), 0))
        forecast_orders = float(self.forecast_slot_orders(location, target, plan.get("daypart_multipliers")).sum())
        return {
            "note": "Leftover cost at close; ignores spoilage from hold times. Synthetic data.",
            "actual_orders": actual_orders,
            "forecast_orders": _r(forecast_orders),
            "ours_leftover_cost_usd": _r(tot["ours_leftover"], 2),
            "manager_leftover_cost_usd": _r(tot["manager_leftover"], 2),
            "ours_runouts": ours_out,
            "manager_runouts": mgr_out,
            "components": rows,
        }

    # ------------------------------------------------------------------ heatmap
    def heatmap(
        self,
        location: str,
        metric: str = "orders",
        channel: str = "all",
        end_date: Optional[str] = None,
        weeks: int = BASELINE_WEEKS,
        include_special: bool = False,
    ) -> Dict[str, Any]:
        end = date.fromisoformat(end_date) if end_date else self.last_date
        start = end - timedelta(days=weeks * 7 - 1)
        lines = self.lines[(self.lines.location == location)]
        if channel != "all":
            lines = lines[lines.source == channel]
        dates = [
            (start + timedelta(days=i)).isoformat()
            for i in range((end - start).days + 1)
        ]
        dates = [d for d in dates if self.has_data(location, d) and (include_special or not self.is_special(d))]
        lines = lines[lines.date.isin(dates)]
        if metric == "orders":
            per = lines.groupby(["date", "slot"]).order_id.nunique()
        else:
            per = lines[lines.item_id == metric].groupby(["date", "slot"]).qty.sum()
        slots = list(range(10 * 4, 24 * 4))
        rows = []
        for wd in range(7):
            wd_dates = [d for d in dates if date.fromisoformat(d).weekday() == wd]
            vals = []
            for sl in slots:
                tot = sum(per.get((d, sl), 0) for d in wd_dates)
                vals.append(_r(tot / len(wd_dates), 2) if wd_dates else 0.0)
            rows.append({"day": WEEKDAYS[wd][:3], "days_averaged": len(wd_dates), "values": vals})
        return {
            "location": location,
            "metric": metric if metric == "orders" else self.menu_names.get(metric, metric),
            "channel": channel,
            "window": {"start": start.isoformat(), "end": end.isoformat()},
            "include_special_days": include_special,
            "slots": [slot_label(s) for s in slots],
            "rows": rows,
        }

    def meta(self) -> Dict[str, Any]:
        return {
            "data_label": "SYNTHETIC",
            "locations": self.location_keys,
            "date_range": {"start": self.first_date.isoformat(), "end": self.last_date.isoformat()},
            "dayparts": {k: [minute_label(a), minute_label(b)] for k, (a, b) in DAYPARTS.items()},
            "menu": [{"id": i, "name": n} for i, n in self.menu_names.items()],
            "components": [
                {"id": cid, "name": r.component_name, "unit": r.unit} for cid, r in self.comp.iterrows()
            ],
            "special_days": self.special_day_labels(),
        }


@lru_cache(maxsize=1)
def get_store() -> DataStore:
    return DataStore()
