# Recommendations Spec — Dreadheads (NOVA 2026)

What the agent produces from historical DoorDash + Grubhub order data, how each output is computed, and what the UI shows.

**Core principle:** plain Python does the counting and math. The LLM agent adjusts for context it can't get from history alone (holidays, games, weather) and explains every recommendation in plain English. The agent never invents numbers; it starts from the baseline and must give a reason for every change.

**Data freshness constraint:** DoorDash reports refresh daily and Grubhub can lag 1–2 days, so everything here is **planned from history**, not reacted to live. Live in-service adjustment is out of scope.

---

## 1. Inputs

### From the platforms (normalized, see `restaurant-api-data-handoff.md`)

Table `order_lines`, one row per item line:

| Field | Notes |
|---|---|
| `source` | `doordash` or `grubhub` |
| `store_id` | string |
| `order_id` | string; count **distinct** for order volume |
| `placed_at_local` | local timestamp; derive weekday, hour, 15-min slot |
| `canonical_item` | from `menu_map` (platform item names matched to one menu) |
| `quantity` | sum for dish volume |
| `unit_price` | not summed across rows |
| `fulfillment` | pickup vs delivery |
| `modifiers` | Grubhub only; DoorDash has no documented modifier column |

### From the manager (entered once in the UI)

| Table | Fields | Used for |
|---|---|---|
| `recipes` | item, ingredient, amount per serving, unit | dishes to ingredients |
| `ingredients` | name, unit, batch size, cook/prep time (min), hold time (min), supplier, pack size, lead time (days) | timeline, prep order, ordering |
| `on_hand` | ingredient, quantity, counted_at | need minus have |
| `context_calendar` | date, label (holiday / Steelers home game / weather) | agent adjustments |

All demo data is **synthetic** and labeled as such.

---

## 2. Shared building blocks

**Dayparts:** lunch 11:00–14:00, afternoon 14:00–17:00, dinner 17:00–21:00 (configurable).

**Baseline forecast** for target date `D`, item `i`, 15-min slot `s`:
- Average `quantity` for `i` in slot `s` over the last **8 same weekdays**.
- Exclude days in `context_calendar` (holidays, games) so special days don't distort a normal baseline.
- Roll slots up to dayparts and the full day as needed.

**Agent adjustment:**
- The agent receives the baseline plus the context for `D`.
- It can call a tool to look up past similar days (e.g., the last 3 Steelers home games) and compare them to their own baseline.
- It returns a multiplier per item or daypart, bounded to **0.5×–2.0×**, with a reason and a confidence (`low` / `medium` / `high`).

**Dishes to ingredients:**
`ingredient_need = Σ (forecast_qty[item] × amount_per_serving[item, ingredient])`
Optionally bump for modifiers using the Grubhub rate (e.g., 18% of bowls add extra chicken), and label that estimate as Grubhub-only.

**Stock-out detection** (feeds the flags and adjusts the baseline):
An item that normally sells in a slot shows **zero sales for 45+ minutes** during a period when it usually sells, after selling earlier that day. That likely means it ran out, so real demand was higher than recorded. Flag it and suggest an uplift.

---

## 3. Feature 1: Start-of-day prep sheet

**User:** shift / kitchen manager, at open or the night before.

**Shows:** for each daypart, every ingredient with amount to prep, sorted by **hold time (longest first)** so durable items are prepped first and short-hold items last.

**Math:**
```
need     = ingredient_need for the daypart × agent multiplier × (1 + buffer)
to_prep  = max(0, need − on_hand)
rounded  = round up to batch size
```
Default buffer: 10%.

**Output shape:**
```json
{
  "date": "2026-11-08",
  "daypart": "dinner",
  "ingredient": "chicken",
  "need": "14 lb",
  "on_hand": "4 lb",
  "to_prep": "10 lb",
  "reason": "Sunday baseline 11 lb; Steelers home game, last 3 game days ran +20–30%",
  "confidence": "medium"
}
```

---

## 4. Feature 2: Rush timeline (15-minute slots)

**User:** shift manager during service, viewed alongside the prep sheet.

**Shows:** a planned schedule for the day, e.g.
- 4:45: start 2nd batch of chicken (30 min cook; peak starts 5:30)
- 5:30–7:00: peak window, ~60% of dinner orders
- 6:30: last rice batch; demand drops after 7:15

**Math, for each batch-cooked ingredient:**
1. Build the cumulative forecast demand curve in 15-min slots.
2. Batch `k` is needed at the first slot where cumulative demand exceeds `(k − 1) × batch_size`.
3. `start_time = needed_time − cook_time`.
4. Don't schedule a batch earlier than its hold time allows. If two batches would be cooked too far ahead, split them later.
5. Mark the **peak window**: the contiguous slots holding the top share of daypart orders.

**Output shape:**
```json
{
  "time": "16:45",
  "action": "Start batch 2 of chicken",
  "ingredient": "chicken",
  "reason": "Cumulative demand passes batch 1 by ~17:15; 30 min cook time"
}
```

---

## 5. Feature 3: Heads-up flags

Shown as 2–4 short bullets at the top of the prep sheet, ranked by impact. Types:

| Type | Example |
|---|---|
| `event` | Steelers home game: expect +25%, mostly wings and burritos |
| `stockout_risk` | Chicken likely sold out ~7:30 the last two Fridays; prep extra |
| `channel_shift` | Delivery rises from 40% to 70% of orders after 7 PM; stock packaging |
| `unusual_day` | Holiday with only 1 past example; forecast is low confidence |

**Output shape:**
```json
{
  "type": "stockout_risk",
  "message": "Chicken likely sold out ~7:30 PM the last two Fridays",
  "action": "Prep 20% extra chicken for dinner",
  "evidence": "Zero chicken sales 7:30–9:00 on 10/30 and 11/6 vs ~6 per slot normally"
}
```

---

## 6. Feature 4: Rush-hour heatmap

**User:** manager and owner.

**Shows:** a grid with **days of the week as rows** and **15-min slots as columns** (e.g., 10:00–22:00). Color = average **distinct orders** per slot over the last 8 weeks. Peaks jump out visually.

**Controls:**
- Channel filter: all / DoorDash / Grubhub
- Metric toggle: orders vs. a single item's quantity (e.g., "chicken bowls only")
- Option to include or exclude special days from `context_calendar`

**Data:** computed in plain Python/SQL. No LLM needed.

**Output shape:**
```json
{
  "metric": "orders",
  "channel": "all",
  "slots": ["10:00", "10:15", "..."],
  "rows": [
    {"day": "Mon", "values": [0.4, 0.9, "..."]},
    {"day": "Tue", "values": [0.5, 1.1, "..."]}
  ]
}
```

---

## 7. Feature 5: Weekly owner summary + order list

**User:** owner, once a week (e.g., Sunday night).

**Sections:**
1. **Week in review:** total orders, channel split, busiest day and slot, forecast vs. actual (using the lagged report data).
2. **Trends:** items up or down 3+ weeks in a row.
3. **Slow movers:** items with consistently low sales that may be over-prepped.
4. **Stock-out recap:** items flagged as likely sold out this week.
5. **Ingredients to order for next week.**

**Order list math:**
```
next_week_usage = Σ over next 7 days of ingredient_need × agent multiplier
safety_stock    = 10–15% of next_week_usage (agent can raise it for known events)
to_order        = max(0, next_week_usage + safety_stock − expected_on_hand)
rounded         = round up to supplier pack size
```
Group by supplier, and flag anything whose lead time means it must be ordered today.

**Output shape:**
```json
{
  "ingredient": "chicken thigh",
  "next_week_usage": "82 lb",
  "safety_stock": "10 lb",
  "on_hand": "12 lb",
  "to_order": "80 lb (2 × 40 lb case)",
  "supplier": "Supplier A",
  "order_by": "2026-11-09",
  "reason": "Steelers home game Sunday adds ~8 lb vs a normal week"
}
```

**Caveat to show in the UI:** sales data doesn't capture waste, spoilage, or true demand on sold-out days, so the order list is a recommendation for the owner to review, not an automatic purchase.

---

## 8. Who does what

| Piece | Plain Python | Agent (LLM) |
|---|---|---|
| Normalize platform CSVs | ✅ | |
| Match platform item names to menu | | ✅ proposes, manager approves |
| Baseline forecast | ✅ | |
| Context adjustment + reasons | | ✅ |
| Dishes to ingredients, need − have | ✅ | |
| Rush timeline scheduling | ✅ | ✅ writes the reasons |
| Stock-out detection | ✅ | ✅ explains |
| Heatmap | ✅ | |
| Weekly summary narrative | | ✅ |
| Order list quantities | ✅ | ✅ adjusts safety stock for events |

---

## 9. Backend endpoints

| Endpoint | Returns |
|---|---|
| `GET /prep-sheet?date=YYYY-MM-DD` | Feature 1 rows + Feature 3 flags |
| `GET /timeline?date=YYYY-MM-DD` | Feature 2 rows |
| `GET /heatmap?metric=orders&channel=all` | Feature 4 grid |
| `GET /weekly-summary?week_start=YYYY-MM-DD` | Feature 5 sections + order list |
| `POST /on-hand` | Save manager's counts |
| `POST /menu-map/approve` | Confirm item matches |

---

## 10. Data handling rules (from the handoff doc)

- Keep IDs as strings.
- Count distinct `order_id` for order volume; sum `quantity` for dish volume. Never sum `subtotal` across item rows.
- Confirm timezone handling before deriving local hour and weekday.
- Deduplicate overlapping report pulls.
- Treat modifier-based adjustments as Grubhub-only estimates.
- Label synthetic data. It supports the demo but can't prove real-world accuracy.

---

## 11. Demo script (~3 min)

1. Show the two raw CSVs with different column names; then the unified data.
2. Heatmap: point out Friday/Saturday dinner peaks and the delivery-heavy late slots.
3. Prep sheet for a normal Tuesday, sorted by hold time.
4. Switch to a Steelers Sunday: amounts jump, flags explain why, timeline moves batch starts earlier.
5. Weekly owner summary: trends, stock-out recap, and next week's order list grouped by supplier.

## 12. Out of scope (future work)

- Live in-service updates from order webhooks
- Camera-based food level monitoring
- Labor scheduling
- Wait-time, cancellation, and item-error reports
