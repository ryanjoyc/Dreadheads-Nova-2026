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
| `recipes` | item, ingredient, amount per serving, unit, `required` (can the dish go out without it? default yes) | dishes to ingredients; which dishes a shortage blocks |
| `ingredients` | name, unit, batch size, cook/prep time (min), hold time (min), supplier, pack size, lead time (days) | timeline, prep order, ordering |
| `on_hand` | ingredient, quantity, counted_at | need minus have |
| `context_calendar` | date, label (holiday / Steelers home game / weather) | agent adjustments |
| `crew` | name, role (`shift_manager` / `crew`), shifts, tablet or phone to notify | who gets the pre-rush stock check |

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

## 6. Feature 4: Pre-rush stock check

**User:** the shift manager on duty, or a crew member if the manager doesn't answer.

**Purpose:** before each rush, ask the kitchen whether it has enough of the ingredients the rush's most-ordered dishes depend on. Then rank the shortfalls and name the **top 3 ingredients to prep first**.

### When and who

- **Send time** = `rush_start − lead`, where `lead` = the longest prep duration among the rush's required ingredients + 15 min (minimum 45 min). It is never sent before the previous rush ends; if that clips the lead, the long-prep ingredient is already covered by early prep.
  Example: Craig St dinner starts 17:00, barbacoa takes 180 min, lunch ends 14:00 → the check goes out at **14:00**.
- **Recipient:** the shift manager on shift in `crew`. If there's no answer in 10 min, the check goes to the next crew member on shift. If nobody answers in 20 min, the tablet shows the top 3 by orders at risk, marked **unchecked**.
- **Delivery:** a notification on the prep tablet (and the phone in `crew`, if set). The check is one screen and takes under a minute.

### What the crew answers

Only the ingredients that matter for this rush: the **8 required ingredients with the highest orders at risk** (below). The 4 optional ones are left off. For each, the crew taps:

| Answer | Shortfall used |
|---|---|
| **Enough** | 0 |
| **Low** | 0.5 |
| **Out** | 1.0 |
| Enter a count (optional) | `max(0, need − count) / need` |

Counts are saved through `POST /on-hand` and also feed Feature 1. Answers never change the prep list's counts or its list order (see GLOSSARY: nobody edits or checks off a count).

### Ranking math

For rush `R` with forecast dish portions `f[i]` (baseline × agent multiplier, same as Feature 1) and ingredient `g`:

```
need[g]          = Σ_i f[i] × amount_per_serving[i, g]
orders_at_risk[g] = Σ f[i] over dishes i where g is required
risk_share[g]     = orders_at_risk[g] / Σ_i f[i]                  0–1: how much of the rush this ingredient blocks
shortfall[g]      = from the crew's answer                        0–1
time_pressure[g]  = min(1, prep_minutes[g] / minutes_until_rush)  1 = one batch can't finish before the rush
score[g]          = risk_share × shortfall × (1 + time_pressure)  0–2
```

- **Top 3** = the three highest scores with `shortfall > 0`. Ties go to the longer prep duration.
- If fewer than 3 ingredients are short, the remaining slots show the highest `risk_share` items marked **covered**, so the crew knows what to keep an eye on.
- If `time_pressure = 1` and the ingredient is short, the action changes from "prep now" to "**can't finish before the rush**." The agent suggests pushing other dishes or 86ing the item at an estimated time. The estimate is the slot where cumulative forecast demand passes on-hand, from the Feature 2 curve.
- Weighting by orders blocked, not by quantity, keeps garnishes and sauces from outranking the protein that ten bowls depend on. Dishes with no ingredients, such as drinks, are left out of the total.

### Worked example (synthetic data)

Craig St, Friday dinner 17:00–21:00, based on the last 8 Fridays: ~84 orders, ~174 dish portions, with wings, chicken bowls, and barbacoa bowls on top. The check is answered at 14:00, so `minutes_until_rush` = 180.

| Ingredient | Need | On hand | Risk share | Shortfall | Time pressure | Score | Rank |
|---|---|---|---|---|---|---|---|
| Braised barbacoa | 152 oz | 60 oz | 0.24 | 0.60 | 1.00 | 0.29 | **1** |
| Cilantro-lime rice | 327 oz | 180 oz | 0.34 | 0.45 | 0.22 | 0.19 | **2** |
| Fries (blanched) | 334 oz | 200 oz | 0.32 | 0.40 | 0.19 | 0.15 | **3** |
| Tortillas | 54 | 30 | 0.16 | 0.45 | 0.03 | 0.08 | 4 |
| Wings | 211 | 120 | 0.12 | 0.43 | 0.22 | 0.06 | 5 |
| Chicken, beans, patties, buns | — | enough | — | 0 | — | 0 | — |

Wings are the single most-ordered dish but rank 5th, because only one dish needs them. Barbacoa ranks 1st because its 3-hour braise has to start right now.

### Output shape

```json
{
  "rush": "dinner",
  "date": "2026-11-13",
  "checked_by": "shift_manager",
  "checked_at": "14:03",
  "status": "answered",
  "priorities": [
    {
      "rank": 1,
      "ingredient": "braised beef barbacoa",
      "need": "152 oz",
      "on_hand": "60 oz",
      "to_prep": "1 batch (96 oz)",
      "score": 0.29,
      "action": "Start barbacoa now — 3 hr braise finishes right at 17:00",
      "reason": "Barbacoa bowls and tacos are ~24% of Friday dinner portions; 60 oz covers about the first hour"
    }
  ]
}
```

The agent writes `action` and `reason`. Plain Python computes every number.

### UI

- A **"Prep these first"** card at the top of the next-rush prep list: three rows, each with an ingredient, the action, and a one-line reason.
- The card sits above the prep list and doesn't reorder it.
- Each row is labeled with who answered and when, or with **unchecked**.

---

## 7. Feature 5: Rush-hour heatmap

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

## 8. Feature 6: Weekly owner summary + order list

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

## 9. Who does what

| Piece | Plain Python | Agent (LLM) |
|---|---|---|
| Normalize platform CSVs | ✅ | |
| Match platform item names to menu | | ✅ proposes, manager approves |
| Baseline forecast | ✅ | |
| Context adjustment + reasons | | ✅ |
| Dishes to ingredients, need − have | ✅ | |
| Rush timeline scheduling | ✅ | ✅ writes the reasons |
| Stock-out detection | ✅ | ✅ explains |
| Pre-rush stock check: send time, scores, top 3 | ✅ | |
| Stock check: actions and reasons, can't-make-in-time advice | | ✅ |
| Heatmap | ✅ | |
| Weekly summary narrative | | ✅ |
| Order list quantities | ✅ | ✅ adjusts safety stock for events |

---

## 10. Backend endpoints

| Endpoint | Returns |
|---|---|
| `GET /prep-sheet?date=YYYY-MM-DD` | Feature 1 rows + Feature 3 flags |
| `GET /timeline?date=YYYY-MM-DD` | Feature 2 rows |
| `GET /heatmap?metric=orders&channel=all` | Feature 4 grid |
| `GET /weekly-summary?week_start=YYYY-MM-DD` | Feature 5 sections + order list |
| `POST /on-hand` | Save manager's counts |
| `GET /rush-check?date=YYYY-MM-DD&rush=dinner` | Feature 4: the ingredients to ask about, send time, recipient |
| `POST /rush-check` | Save the crew's Enough / Low / Out answers (or counts); returns the ranked top 3 |
| `POST /menu-map/approve` | Confirm item matches |

---

## 11. Data handling rules (from the handoff doc)

- Keep IDs as strings.
- Count distinct `order_id` for order volume; sum `quantity` for dish volume. Never sum `subtotal` across item rows.
- Confirm timezone handling before deriving local hour and weekday.
- Deduplicate overlapping report pulls.
- Treat modifier-based adjustments as Grubhub-only estimates.
- Label synthetic data. It supports the demo but can't prove real-world accuracy.

---

## 12. Demo script (~3 min)

1. Show the two raw CSVs with different column names; then the unified data.
2. Heatmap: point out Friday/Saturday dinner peaks and the delivery-heavy late slots.
3. Prep sheet for a normal Tuesday, sorted by hold time.
4. Switch to a Steelers Sunday: amounts jump, flags explain why, timeline moves batch starts earlier.
5. Pre-rush stock check at 14:00 on a Friday: the manager taps Low on barbacoa and rice, and the top 3 appears with "start barbacoa now."
6. Weekly owner summary: trends, stock-out recap, and next week's order list grouped by supplier.

## 13. Out of scope (future work)

- Live in-service updates from order webhooks
- Camera-based food level monitoring
- Labor scheduling
- Wait-time, cancellation, and item-error reports
