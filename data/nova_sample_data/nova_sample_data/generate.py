"""
Nova synthetic restaurant dataset generator.

ALL DATA PRODUCED HERE IS SYNTHETIC. It mimics the DoorDash ORDER_DETAIL and
Grubhub menu-line-items report schemas from the Nov 7 2026 API handoff doc, so
the analytics platform can be built before real merchant access exists. It
cannot be used to establish real-world forecast accuracy.

Usage:  python generate.py [--start 2026-05-01] [--end 2026-10-31] [--seed 7] [--out data]
"""
import argparse
import json
import math
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

TZ = "America/New_York"
TZI = ZoneInfo(TZ)
UTC = ZoneInfo("UTC")

BUSINESS_NAME = "Steel City Bowls (SYNTHETIC)"
DD_BUSINESS_ID = "5501928"

# ---------------------------------------------------------------------------
# Locations
# ---------------------------------------------------------------------------
LOCATIONS = [
    {
        "location_key": "craig",
        "store_name": "Steel City Bowls - Craig St",
        "store_number": "001",
        "dd_store_id": "24418903",
        "gh_store_id": "3184472",
        "external_id": "SCB-001",
        "base_orders_per_day": 150,
        # Student-heavy: big dinner and late-night, Grubhub-leaning (campus)
        "doordash_share": 0.45,
        "student_sensitivity": 1.0,
        "hours": {  # weekday 0=Mon: (open_hour, close_hour)
            0: (10.5, 22), 1: (10.5, 22), 2: (10.5, 22), 3: (10.5, 24),
            4: (10.5, 24), 5: (10.5, 24), 6: (11, 22),
        },
    },
    {
        "location_key": "strip",
        "store_name": "Steel City Bowls - Strip District",
        "store_number": "002",
        "dd_store_id": "24418977",
        "gh_store_id": "3184519",
        "external_id": "SCB-002",
        "base_orders_per_day": 110,
        # Office/lunch and weekend-tourist heavy, DoorDash-leaning
        "doordash_share": 0.62,
        "student_sensitivity": 0.25,
        "hours": {d: (11, 21) for d in range(7)},
    },
]

# ---------------------------------------------------------------------------
# Menu, prep components, recipes (the "separate source" the doc says sales
# data cannot provide)
# ---------------------------------------------------------------------------
# prep components: things the line preps ahead in batches
COMPONENTS = [
    # id, name, unit, batch_yield, prep_minutes, hold_hours, unit_cost, raw_ingredients, supplier_lead_days
    ("C01", "Marinated grilled chicken", "oz", 64, 45, 6, 0.32, "chicken thigh, garlic, lemon, spice blend", 2),
    ("C02", "Braised beef barbacoa", "oz", 96, 180, 8, 0.55, "beef chuck, chipotle, onion, stock", 3),
    ("C03", "Crispy tofu", "oz", 20, 30, 4, 0.18, "firm tofu, cornstarch, oil", 2),
    ("C04", "Fried chicken tenders (breaded)", "pc", 20, 25, 3, 0.60, "chicken tenderloin, flour, buttermilk", 2),
    ("C05", "Smash burger patties (portioned)", "pc", 24, 20, 24, 1.05, "ground beef 80/20", 2),
    ("C06", "Cilantro-lime rice", "oz", 120, 40, 4, 0.06, "jasmine rice, lime, cilantro", 5),
    ("C07", "Black beans", "oz", 96, 30, 8, 0.05, "black beans, cumin, onion", 7),
    ("C08", "Pico de gallo", "oz", 64, 25, 12, 0.12, "tomato, onion, jalapeno, cilantro", 2),
    ("C09", "Pickled red onion", "oz", 48, 15, 72, 0.08, "red onion, vinegar, sugar", 4),
    ("C10", "Shredded lettuce", "oz", 32, 10, 24, 0.04, "romaine", 2),
    ("C11", "Queso sauce", "oz", 32, 20, 6, 0.15, "cheddar, milk, chiles", 4),
    ("C12", "Chipotle crema", "oz", 48, 10, 48, 0.10, "sour cream, chipotle, lime", 4),
    ("C13", "Hand-cut fries (blanched)", "oz", 120, 35, 6, 0.05, "russet potatoes, oil", 3),
    ("C14", "Buffalo wing sauce", "oz", 32, 10, 72, 0.07, "hot sauce, butter", 5),
    ("C15", "Wings (par-cooked)", "pc", 40, 40, 6, 0.42, "chicken wings", 2),
    ("C16", "Guacamole", "oz", 24, 20, 6, 0.28, "avocado, lime, onion, cilantro", 2),
    ("C17", "Tortillas (warmed stack)", "pc", 24, 5, 4, 0.12, "flour tortillas", 5),
    ("C18", "Brioche buns", "pc", 24, 2, 48, 0.35, "brioche buns", 3),
    ("C19", "Breakfast egg scramble", "oz", 8, 15, 2, 0.14, "eggs, butter", 3),
    ("C20", "Cookie dough (portioned)", "pc", 24, 15, 72, 0.30, "flour, butter, sugar, chocolate", 7),
]

# menu items: id, name, category, price, complexity (prep-minute multiplier), daypart weights (brunch, lunch, afternoon, dinner, late)
MENU = [
    ("M01", "Chicken Burrito Bowl", "Bowls", 12.49, 1.0, (0.9, 1.3, 1.0, 1.1, 0.7)),
    ("M02", "Barbacoa Bowl", "Bowls", 13.99, 1.0, (0.6, 1.1, 0.9, 1.3, 0.8)),
    ("M03", "Crispy Tofu Bowl", "Bowls", 11.99, 1.0, (0.7, 1.1, 1.0, 0.9, 0.5)),
    ("M04", "Chicken Burrito", "Burritos & Tacos", 11.99, 1.1, (0.9, 1.2, 1.0, 1.1, 1.1)),
    ("M05", "Barbacoa Tacos (3)", "Burritos & Tacos", 12.49, 1.2, (0.4, 0.9, 0.8, 1.3, 1.2)),
    ("M06", "Breakfast Burrito", "Burritos & Tacos", 9.99, 1.0, (3.5, 0.6, 0.2, 0.1, 0.4)),
    ("M07", "Smash Burger", "Burgers", 11.49, 1.3, (0.3, 1.0, 0.9, 1.3, 1.5)),
    ("M08", "Double Smash Burger", "Burgers", 14.49, 1.4, (0.2, 0.8, 0.8, 1.3, 1.7)),
    ("M09", "Chicken Tender Basket", "Baskets", 12.99, 1.2, (0.3, 0.9, 1.1, 1.1, 1.6)),
    ("M10", "Buffalo Wings (10)", "Baskets", 14.99, 1.3, (0.1, 0.6, 0.8, 1.4, 2.2)),
    ("M11", "Loaded Queso Fries", "Sides", 8.49, 0.8, (0.2, 0.7, 1.1, 1.0, 2.0)),
    ("M12", "Fries", "Sides", 4.49, 0.5, (0.3, 1.0, 1.0, 1.0, 1.3)),
    ("M13", "Chips & Guac", "Sides", 5.99, 0.4, (0.5, 1.0, 1.2, 0.9, 0.9)),
    ("M14", "Chocolate Chip Cookie", "Desserts", 2.99, 0.3, (0.4, 0.8, 1.2, 1.0, 1.5)),
    ("M15", "Fountain Drink", "Drinks", 2.49, 0.1, (0.8, 1.2, 1.1, 1.0, 0.9)),
]
MENU_BASE_POPULARITY = {
    "M01": 1.6, "M02": 1.0, "M03": 0.55, "M04": 1.2, "M05": 0.8, "M06": 0.5,
    "M07": 1.1, "M08": 0.7, "M09": 0.9, "M10": 0.8, "M11": 0.6, "M12": 1.0,
    "M13": 0.6, "M14": 0.7, "M15": 1.1,
}
# location-specific popularity tilt
LOCATION_TILT = {
    "craig": {"M10": 1.35, "M11": 1.4, "M08": 1.25, "M03": 0.8},
    "strip": {"M03": 1.4, "M01": 1.15, "M10": 0.7, "M11": 0.7},
}

# recipe: menu_item -> [(component_id, qty_per_item)]
RECIPES = {
    "M01": [("C01", 4), ("C06", 6), ("C07", 4), ("C08", 2), ("C10", 1.5), ("C12", 1)],
    "M02": [("C02", 4), ("C06", 6), ("C07", 4), ("C08", 2), ("C09", 1), ("C12", 1)],
    "M03": [("C03", 5), ("C06", 6), ("C07", 4), ("C08", 2), ("C09", 1), ("C10", 1.5)],
    "M04": [("C01", 4), ("C06", 4), ("C07", 3), ("C08", 1.5), ("C12", 1), ("C17", 1)],
    "M05": [("C02", 4.5), ("C08", 2), ("C09", 1), ("C12", 1), ("C17", 3)],
    "M06": [("C19", 4), ("C08", 1), ("C13", 3), ("C17", 1), ("C12", 0.5)],
    "M07": [("C05", 1), ("C18", 1), ("C10", 0.5), ("C09", 0.5)],
    "M08": [("C05", 2), ("C18", 1), ("C10", 0.5), ("C09", 0.5)],
    "M09": [("C04", 4), ("C13", 6), ("C12", 1)],
    "M10": [("C15", 10), ("C14", 2.5), ("C13", 4)],
    "M11": [("C13", 8), ("C11", 3), ("C02", 2), ("C08", 1), ("C12", 1)],
    "M12": [("C13", 8)],
    "M13": [("C16", 4)],
    "M14": [("C20", 1)],
    "M15": [],
}

# modifiers: id, name, price, applies_to (menu ids), attach_rate, extra component usage
MODIFIERS = [
    ("MOD01", "Extra chicken", 3.00, {"M01", "M04"}, 0.14, [("C01", 3)]),
    ("MOD02", "Extra barbacoa", 3.50, {"M02", "M05"}, 0.12, [("C02", 3)]),
    ("MOD03", "Add guacamole", 2.25, {"M01", "M02", "M03", "M04", "M05"}, 0.22, [("C16", 2)]),
    ("MOD04", "Add queso", 1.75, {"M01", "M02", "M04", "M12"}, 0.15, [("C11", 2)]),
    ("MOD05", "Add cheese", 1.00, {"M07", "M08"}, 0.45, []),
    ("MOD06", "Add bacon", 2.00, {"M07", "M08", "M06"}, 0.20, []),
    ("MOD07", "Sauce: Buffalo", 0.00, {"M09"}, 0.35, [("C14", 1)]),
    ("MOD08", "Sauce: Chipotle crema", 0.00, {"M09"}, 0.40, [("C12", 1)]),
    ("MOD09", "No rice", 0.00, {"M01", "M02", "M03"}, 0.06, [("C06", -6)]),
]
MOD_BY_ID = {m[0]: m for m in MODIFIERS}


# ---------------------------------------------------------------------------
# Demand shape
# ---------------------------------------------------------------------------
def hourly_curve(hour_float, weekday, loc_key):
    """Relative order intensity at a local time of day (hours as float)."""
    h = hour_float
    lunch = 1.0 * math.exp(-((h - 12.3) ** 2) / (2 * 0.75 ** 2))
    dinner = 1.15 * math.exp(-((h - 18.6) ** 2) / (2 * 1.0 ** 2))
    afternoon = 0.18 * math.exp(-((h - 15.3) ** 2) / (2 * 1.2 ** 2))
    brunch = 0.0
    late = 0.0
    if weekday in (5, 6):  # weekend: wider, later lunch / brunch
        lunch = 0.95 * math.exp(-((h - 12.9) ** 2) / (2 * 1.15 ** 2))
        brunch = 0.25 * math.exp(-((h - 10.9) ** 2) / (2 * 0.6 ** 2))
    if loc_key == "craig":
        dinner *= 1.15
        lunch *= 0.85
        if weekday in (3, 4, 5):  # Thu/Fri/Sat late night
            late = 0.75 * math.exp(-((h - 22.6) ** 2) / (2 * 0.8 ** 2))
    else:
        lunch *= 1.25 if weekday < 5 else 1.0
        dinner *= 0.8
    return 0.03 + lunch + dinner + afternoon + brunch + late


WEEKDAY_MULT = {0: 0.82, 1: 0.88, 2: 0.95, 3: 1.04, 4: 1.25, 5: 1.22, 6: 1.02}


def daypart(h):
    if h < 11:
        return 0
    if h < 14.5:
        return 1
    if h < 17:
        return 2
    if h < 21:
        return 3
    return 4


# ---------------------------------------------------------------------------
# Outside signals (synthetic)
# ---------------------------------------------------------------------------
HOLIDAYS = {
    date(2026, 5, 25): ("Memorial Day", 0.80),
    date(2026, 6, 19): ("Juneteenth", 0.92),
    date(2026, 7, 4): ("Independence Day", 0.55),
    date(2026, 9, 7): ("Labor Day", 0.78),
    date(2026, 10, 31): ("Halloween", 1.10),
}
# Fabricated local events (dates are illustrative, NOT real schedules)
EVENTS = {
    date(2026, 9, 13): ("Pro football home game (synthetic)", {"craig": 1.15, "strip": 1.45}),
    date(2026, 9, 27): ("Pro football home game (synthetic)", {"craig": 1.15, "strip": 1.45}),
    date(2026, 10, 11): ("Pro football home game (synthetic)", {"craig": 1.15, "strip": 1.45}),
    date(2026, 10, 25): ("Pro football home game (synthetic)", {"craig": 1.15, "strip": 1.45}),
    date(2026, 7, 18): ("Strip District food festival (synthetic)", {"craig": 1.0, "strip": 1.6}),
    date(2026, 7, 19): ("Strip District food festival (synthetic)", {"craig": 1.0, "strip": 1.5}),
    date(2026, 8, 22): ("University move-in weekend (synthetic)", {"craig": 1.35, "strip": 1.0}),
    date(2026, 8, 23): ("University move-in weekend (synthetic)", {"craig": 1.40, "strip": 1.0}),
    date(2026, 10, 9): ("University fall break start (synthetic)", {"craig": 0.75, "strip": 1.0}),
    date(2026, 10, 10): ("University fall break (synthetic)", {"craig": 0.7, "strip": 1.0}),
    date(2026, 10, 11): ("University fall break (synthetic)", {"craig": 0.7, "strip": 1.0}),
}
SEMESTER_START = date(2026, 8, 24)
SPRING_END = date(2026, 5, 15)


def build_daily_context(days, rng):
    rows = []
    temp = 62.0
    for d in days:
        # seasonal temperature + AR noise
        season = 58 + 22 * math.sin((d.timetuple().tm_yday - 105) / 365 * 2 * math.pi)
        temp = 0.6 * temp + 0.4 * season + rng.normal(0, 4)
        rain_prob = 0.32
        precip_in = 0.0
        if rng.random() < rain_prob:
            precip_in = round(float(rng.gamma(1.2, 0.18)), 2)
        in_session = (d <= SPRING_END) or (d >= SEMESTER_START)
        if d in [date(2026, 10, 9), date(2026, 10, 10), date(2026, 10, 11)]:
            in_session = False
        hol = HOLIDAYS.get(d)
        ev = EVENTS.get(d)
        rows.append({
            "date": d.isoformat(),
            "weekday": d.strftime("%A"),
            "high_temp_f": round(temp + 8, 1),
            "precip_in": precip_in,
            "weather": "rain" if precip_in >= 0.1 else ("drizzle" if precip_in > 0 else ("hot" if temp + 8 > 86 else "clear")),
            "university_in_session": in_session,
            "holiday": hol[0] if hol else "",
            "local_event": ev[0] if ev else "",
        })
    return pd.DataFrame(rows)


def day_multiplier(ctx_row, loc):
    d = date.fromisoformat(ctx_row["date"])
    m = WEEKDAY_MULT[d.weekday()]
    # students: summer is much quieter at Craig
    if not ctx_row["university_in_session"]:
        m *= 1 - 0.38 * loc["student_sensitivity"]
    # rain pushes delivery up, heat a little down
    if ctx_row["precip_in"] >= 0.1:
        m *= 1.16
    elif ctx_row["precip_in"] > 0:
        m *= 1.06
    if ctx_row["high_temp_f"] > 88:
        m *= 0.94
    hol = HOLIDAYS.get(d)
    if hol:
        m *= hol[1]
    ev = EVENTS.get(d)
    if ev:
        m *= ev[1][loc["location_key"]]
    # slow growth trend (~8% over the window)
    m *= 1 + 0.08 * ((d - date(2026, 5, 1)).days / 184)
    return m


# ---------------------------------------------------------------------------
# Staffing (a fixed, imperfect schedule so understaffed rushes show up)
# ---------------------------------------------------------------------------
def staff_on_shift(loc_key, weekday, hour):
    if loc_key == "craig":
        if hour < 11:
            s = 2
        elif hour < 14:
            s = 4
        elif hour < 17:
            s = 2
        elif hour < 21:
            s = 5
        else:
            s = 3  # thin late-night crew, even Thu-Sat
        if weekday in (4, 5) and 17 <= hour < 21:
            s = 6
    else:
        if hour < 11:
            s = 2
        elif hour < 14:
            s = 4 if weekday < 5 else 4
        elif hour < 17:
            s = 2
        else:
            s = 3
    return s


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------
def gen(start, end, seed, out):
    rng = np.random.default_rng(seed)
    days = [start + timedelta(n) for n in range((end - start).days + 1)]
    ctx = build_daily_context(days, rng)
    ctx_by_date = {r["date"]: r for r in ctx.to_dict("records")}

    menu_ids = [m[0] for m in MENU]
    menu = {m[0]: m for m in MENU}

    dd_rows, gh_rows, tickets = [], [], []
    dd_order_seq = 10_000_000
    gh_order_seq = 50_000_000
    mx_seq = 7000

    for loc in LOCATIONS:
        lk = loc["location_key"]
        tilt = LOCATION_TILT[lk]
        for d in days:
            c = ctx_by_date[d.isoformat()]
            wd = d.weekday()
            open_h, close_h = loc["hours"][wd]
            # minute grid intensities
            minutes = np.arange(int(open_h * 60), int(close_h * 60))
            hours_f = minutes / 60.0
            inten = np.array([hourly_curve(h, wd, lk) for h in hours_f])
            if d == date(2026, 10, 31):  # Halloween late spike
                inten = inten + np.where(hours_f > 20.5, 0.35, 0)
            inten = inten / inten.sum()
            expected = loc["base_orders_per_day"] * day_multiplier(c, loc)
            n_orders = rng.poisson(expected)
            picked = np.sort(rng.choice(minutes, size=n_orders, p=inten))

            for minute in picked:
                second = int(rng.integers(0, 60))
                local_dt = datetime(d.year, d.month, d.day, tzinfo=TZI) + timedelta(minutes=int(minute), seconds=second)
                h = local_dt.hour + local_dt.minute / 60
                dp = daypart(h)
                # items in cart (distinct lines) and quantities
                n_lines = 1 + rng.poisson(0.9 if dp != 4 else 1.2)
                n_lines = min(n_lines, 5)
                w = np.array([MENU_BASE_POPULARITY[i] * tilt.get(i, 1.0) * menu[i][5][dp] for i in menu_ids])
                w = w / w.sum()
                line_items = rng.choice(menu_ids, size=n_lines, replace=False, p=w)
                lines = []
                for mid in line_items:
                    qty = 1 + int(rng.random() < 0.12) + int(rng.random() < 0.03)
                    if mid == "M15":
                        qty = 1 + int(rng.random() < 0.35)
                    mods = []
                    for mod in MODIFIERS:
                        if mid in mod[3] and rng.random() < mod[4]:
                            mods.append(mod[0])
                    # sauce choices are exclusive
                    if "MOD07" in mods and "MOD08" in mods:
                        mods.remove("MOD08")
                    lines.append((mid, qty, mods))

                is_pickup = rng.random() < (0.22 if lk == "craig" else 0.30)
                channel = "doordash" if rng.random() < loc["doordash_share"] else "grubhub"
                subtotal = round(sum((menu[mid][3] + sum(MOD_BY_ID[m][2] for m in mods)) * q for mid, q, mods in lines), 2)
                utc_dt = local_dt.astimezone(UTC)

                if channel == "doordash":
                    dd_order_seq += int(rng.integers(1, 40))
                    order_id = f"{dd_order_seq:x}".upper().rjust(8, "0")
                    mx_order = ""
                    ext = ""
                    if rng.random() < 0.85:  # POS ids can be null
                        mx_seq += 1
                        mx_order = str(mx_seq)
                        ext = f"POS-{lk.upper()}-{mx_seq}"
                    dashpass = bool(rng.random() < 0.38)
                    for li, (mid, qty, mods) in enumerate(lines):
                        mi = menu[mid]
                        mod_price = sum(MOD_BY_ID[m][2] for m in mods)
                        dd_rows.append({
                            "business_id": DD_BUSINESS_ID,
                            "store_id": loc["dd_store_id"],
                            "business_name": BUSINESS_NAME,
                            "store_name": loc["store_name"],
                            "dd_order_number": order_id,
                            "order_place_date": local_dt.strftime("%Y-%m-%d"),
                            "order_place_time": local_dt.strftime("%H:%M:%S"),
                            "created_at": utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                            "timezone": TZ,
                            "dd_item_id": f"{9000000000 + int(mid[1:]) * 1117:d}",
                            "item_merchant_supplied_id": mid,
                            "order_item_id": f"{order_id}-{li + 1}",
                            "item_name": mi[1],
                            "category_name": mi[2],
                            "menu_name": "Main Menu",
                            "order_item_quantity": qty,
                            "unit_price": round(mi[3] + mod_price, 2),
                            "original_item_price": mi[3],
                            "subtotal": subtotal,
                            "is_consumer_pickup": is_pickup,
                            "dashpass": dashpass,
                            "mx_order_number": mx_order,
                            "external_order_id": ext,
                        })
                else:
                    gh_order_seq += int(rng.integers(1, 30))
                    order_number = str(gh_order_seq)
                    order_uuid = str(uuid.UUID(int=int(rng.integers(0, 2**63)) << 64 | int(rng.integers(0, 2**63)), version=4))
                    partner_id = f"SCB{gh_order_seq}" if rng.random() < 0.9 else ""
                    for mid, qty, mods in lines:
                        mi = menu[mid]
                        mod_json = json.dumps([
                            {"name": MOD_BY_ID[m][1], "id": m, "price": MOD_BY_ID[m][2], "quantity": 1}
                            for m in mods
                        ]) if mods else "[]"
                        gh_rows.append({
                            "grubhub_store_id": loc["gh_store_id"],
                            "store_name": loc["store_name"],
                            "store_number": loc["store_number"],
                            "external_id": loc["external_id"],
                            "order_number": order_number,
                            "order_uuid": order_uuid,
                            "partner_order_id": partner_id,
                            "order_date": local_dt.strftime("%Y-%m-%d"),
                            "order_time_local": local_dt.strftime("%H:%M:%S"),
                            "order_time_zone": TZ,
                            "menu_item_id": mid,
                            "menu_item_name": mi[1],
                            "menu_item_category_name": mi[2],
                            "menu_item_quantity": qty,
                            "menu_item_price": mi[3],
                            "menu_item_modifiers": mod_json,
                            "fullfillment_type": "PICKUP" if is_pickup else "DELIVERY",
                        })
                    order_id = order_number

                tickets.append({
                    "location_key": lk,
                    "source_platform": channel,
                    "source_order_id": order_id,
                    "placed_at_local": local_dt,
                    "complexity": sum(menu[mid][4] * qty for mid, qty, _ in lines),
                    "is_pickup": is_pickup,
                })

    dd = pd.DataFrame(dd_rows)
    gh = pd.DataFrame(gh_rows)
    tk = build_ticket_log(pd.DataFrame(tickets), rng)
    shifts = build_shifts(days)
    prep_log = build_prep_log(dd, gh, rng)

    out.mkdir(parents=True, exist_ok=True)
    (out / "platform_reports").mkdir(exist_ok=True)
    (out / "reference").mkdir(exist_ok=True)
    (out / "operations").mkdir(exist_ok=True)

    dd.to_csv(out / "platform_reports" / "doordash_order_detail.csv", index=False)
    gh.to_csv(out / "platform_reports" / "grubhub_menu_line_items.csv", index=False)
    write_reference(out / "reference")
    ctx.to_csv(out / "reference" / "daily_context.csv", index=False)
    tk.to_csv(out / "operations" / "kitchen_ticket_log.csv", index=False)
    shifts.to_csv(out / "operations" / "shift_schedule.csv", index=False)
    prep_log.to_csv(out / "operations" / "daily_prep_log.csv", index=False)
    return dd, gh, tk, ctx, prep_log


def build_ticket_log(t, rng):
    """Our own kitchen logging (ideation doc: completion time by time of day).
    Prep time grows when 15-min ticket load outpaces staff on shift."""
    t = t.sort_values(["location_key", "placed_at_local"]).reset_index(drop=True)
    t["bucket"] = t["placed_at_local"].dt.floor("15min")
    load = t.groupby(["location_key", "bucket"])["complexity"].transform("sum")
    hours = t["placed_at_local"].dt.hour
    wds = t["placed_at_local"].dt.weekday
    staff = np.array([staff_on_shift(lk, wd, hr) for lk, wd, hr in zip(t["location_key"], wds, hours)])
    capacity = staff * 3.2  # complexity units one cook clears per 15 min
    util = load / capacity
    base = 6 + 2.2 * t["complexity"]
    congestion = np.clip(util - 0.65, 0, None) * 14
    prep_min = base + congestion + rng.gamma(2, 1.2, len(t))
    accept_delay = rng.gamma(1.5, 0.6, len(t)) + np.clip(util - 0.9, 0, None) * 3
    wait_pickup = np.where(t["is_pickup"], rng.gamma(2, 4, len(t)), rng.gamma(2, 3.2, len(t)) + np.clip(util - 1, 0, None) * 2)
    started = t["placed_at_local"] + pd.to_timedelta(accept_delay, unit="m")
    ready = started + pd.to_timedelta(prep_min, unit="m")
    handed = ready + pd.to_timedelta(wait_pickup, unit="m")
    quoted = np.round(np.clip(base + 4, 10, 30) / 5) * 5
    out = pd.DataFrame({
        "ticket_id": [f"TKT-{i:07d}" for i in range(len(t))],
        "location_key": t["location_key"],
        "source_platform": t["source_platform"],
        "source_order_id": t["source_order_id"].astype(str),
        "placed_at_local": t["placed_at_local"].dt.strftime("%Y-%m-%d %H:%M:%S"),
        "prep_started_at_local": started.dt.strftime("%Y-%m-%d %H:%M:%S"),
        "ready_at_local": ready.dt.strftime("%Y-%m-%d %H:%M:%S"),
        "handed_off_at_local": handed.dt.strftime("%Y-%m-%d %H:%M:%S"),
        "quoted_prep_minutes": quoted.astype(int),
        "actual_prep_minutes": np.round(prep_min, 1),
        "staff_on_line": staff,
        "fulfillment": np.where(t["is_pickup"], "pickup", "delivery"),
    })
    return out


def build_shifts(days):
    rows = []
    for loc in LOCATIONS:
        for d in days:
            wd = d.weekday()
            o, c = loc["hours"][wd]
            for hr in range(int(o), int(math.ceil(c))):
                rows.append({
                    "location_key": loc["location_key"],
                    "date": d.isoformat(),
                    "hour_local": hr,
                    "line_staff_scheduled": staff_on_shift(loc["location_key"], wd, hr),
                })
    return pd.DataFrame(rows)


def explode_component_usage(dd, gh):
    """Item-level sales -> component usage, including modifier adjustments."""
    a = pd.DataFrame({
        "location_key": dd["store_id"].map({l["dd_store_id"]: l["location_key"] for l in LOCATIONS}),
        "date": dd["order_place_date"],
        "hour": dd["order_place_time"].str[:2].astype(int),
        "menu_item_id": dd["item_merchant_supplied_id"],
        "qty": dd["order_item_quantity"],
        "mods": [[] for _ in range(len(dd))],
    })
    # DoorDash export has no modifier column: derive mod usage from price delta
    # is NOT reliable, so we leave DoorDash modifier usage out of component math
    b = pd.DataFrame({
        "location_key": gh["grubhub_store_id"].map({l["gh_store_id"]: l["location_key"] for l in LOCATIONS}),
        "date": gh["order_date"],
        "hour": gh["order_time_local"].str[:2].astype(int),
        "menu_item_id": gh["menu_item_id"],
        "qty": gh["menu_item_quantity"],
        "mods": gh["menu_item_modifiers"].map(lambda s: [m["id"] for m in json.loads(s)]),
    })
    items = pd.concat([a, b], ignore_index=True)
    recs = []
    for r in items.itertuples(index=False):
        for cid, q in RECIPES[r.menu_item_id]:
            recs.append((r.location_key, r.date, r.hour, cid, q * r.qty))
        for m in r.mods:
            for cid, q in MOD_BY_ID[m][5]:
                recs.append((r.location_key, r.date, r.hour, cid, q * r.qty))
    return pd.DataFrame(recs, columns=["location_key", "date", "hour", "component_id", "qty"])


def build_prep_log(dd, gh, rng):
    """Baseline (pre-Nova) behaviour: managers prep to a par of the same weekday
    two weeks ago x1.1, in whole batches, net of what is already on hand.
    Items with hold_hours < 24 are discarded at close; longer-hold items carry
    over and age out at roughly 24/hold_hours of the leftover per day.
    Records waste and the hour each component ran out (the Nova target)."""
    use = explode_component_usage(dd, gh)
    daily = use.groupby(["location_key", "date", "component_id"])["qty"].sum().reset_index()
    comp = {c[0]: c for c in COMPONENTS}
    daily["date_d"] = pd.to_datetime(daily["date"])
    daily = daily.sort_values(["location_key", "component_id", "date_d"])
    daily["ref_qty"] = daily.groupby(["location_key", "component_id"])["qty"].shift(14)
    rows = []
    hourly = use.groupby(["location_key", "date", "component_id", "hour"])["qty"].sum()
    on_hand = {}
    for r in daily.itertuples(index=False):
        c = comp[r.component_id]
        key = (r.location_key, r.component_id)
        opening = on_hand.get(key, 0.0)
        ref = r.ref_qty if not pd.isna(r.ref_qty) else r.qty * rng.uniform(0.95, 1.15)
        target = ref * 1.1 * rng.uniform(0.92, 1.08)
        batches = max(0, math.ceil((target - opening) / c[3]))
        prepped = batches * c[3]
        available = opening + prepped
        used = round(min(r.qty, available), 1)
        unmet = round(max(0.0, r.qty - available), 1)
        ran_out = ""
        if unmet > 0:
            cum = hourly.loc[(r.location_key, r.date, r.component_id)].cumsum()
            hit = cum[cum > available]
            ran_out = f"{int(hit.index[0]):02d}:00" if len(hit) else ""
        leftover = max(0.0, available - used)
        if c[5] < 24:
            waste, carry = leftover, 0.0
        else:
            waste = leftover * min(1.0, 24 / c[5]) * rng.uniform(0.3, 0.7)
            carry = leftover - waste
        on_hand[key] = carry
        rows.append({
            "location_key": r.location_key,
            "date": r.date,
            "component_id": r.component_id,
            "component_name": c[1],
            "unit": c[2],
            "opening_on_hand": round(opening, 1),
            "batches_prepped": batches,
            "qty_prepped": prepped,
            "qty_used": used,
            "qty_demand_unmet": unmet,
            "qty_wasted": round(waste, 1),
            "waste_cost_usd": round(waste * c[6], 2),
            "closing_on_hand": round(carry, 1),
            "ran_out_hour_local": ran_out,
        })
    return pd.DataFrame(rows)


def write_reference(ref):
    pd.DataFrame([{
        "location_key": l["location_key"], "store_name": l["store_name"],
        "store_number": l["store_number"], "doordash_store_id": l["dd_store_id"],
        "grubhub_store_id": l["gh_store_id"], "external_id": l["external_id"],
        "timezone": TZ,
        "hours_by_weekday": json.dumps({str(k): v for k, v in l["hours"].items()}),
    } for l in LOCATIONS]).to_csv(ref / "locations.csv", index=False)
    pd.DataFrame([{
        "menu_item_id": m[0], "menu_item_name": m[1], "category": m[2],
        "price_usd": m[3], "prep_complexity": m[4],
    } for m in MENU]).to_csv(ref / "menu_items.csv", index=False)
    pd.DataFrame([{
        "component_id": c[0], "component_name": c[1], "unit": c[2],
        "batch_yield": c[3], "prep_minutes_per_batch": c[4],
        "hold_hours": c[5], "unit_cost_usd": c[6], "raw_ingredients": c[7],
        "supplier_lead_days": c[8],
    } for c in COMPONENTS]).to_csv(ref / "prep_components.csv", index=False)
    pd.DataFrame([
        {"menu_item_id": mid, "component_id": cid, "qty_per_item": q}
        for mid, lst in RECIPES.items() for cid, q in lst
    ]).to_csv(ref / "recipes.csv", index=False)
    pd.DataFrame([{
        "modifier_id": m[0], "modifier_name": m[1], "price_usd": m[2],
        "applies_to": ",".join(sorted(m[3])),
        "component_adjustments": json.dumps([{"component_id": c, "qty": q} for c, q in m[5]]),
    } for m in MODIFIERS]).to_csv(ref / "modifiers.csv", index=False)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2026-05-01")
    ap.add_argument("--end", default="2026-10-31")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default="data")
    a = ap.parse_args()
    dd, gh, tk, ctx, pl = gen(date.fromisoformat(a.start), date.fromisoformat(a.end), a.seed, Path(a.out))
    print(f"doordash rows {len(dd):,} orders {dd.dd_order_number.nunique():,}")
    print(f"grubhub rows {len(gh):,} orders {gh.order_number.nunique():,}")
    print(f"tickets {len(tk):,}  prep_log {len(pl):,}")
