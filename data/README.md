# Nova sample dataset (SYNTHETIC)

> Every row here is generated. It mirrors the DoorDash and Grubhub report schemas in the
> Nov 7 2026 API handoff doc so we can build the platform before we have merchant access.
> It supports development and demos. It **cannot** be used to claim real-world forecast accuracy.

**Scenario:** "Steel City Bowls," a fictional fast-casual restaurant with two Pittsburgh
locations, May 1 to Oct 31 2026 (184 days, all EDT).

| Location | Character | Hours |
|---|---|---|
| `craig` (Craig St) | Student-heavy. Big dinner rush and a Thu–Sat late-night rush. Quiet in summer. Grubhub-leaning. | 10:30–22:00, until 24:00 Thu–Sat |
| `strip` (Strip District) | Office lunch and weekend crowds. Busy on game days and festival days. DoorDash-leaning. | 11:00–21:00 |

Size: about 45k orders, 86k item rows, and 7.3k component-day prep records.

Regenerate with `python generate.py --start 2026-05-01 --end 2026-10-31 --seed 7 --out data`.
It needs only pandas and numpy.

---

## Files

```
data/
  platform_reports/            <- what the APIs would give us (exact documented fields)
    doordash_order_detail.csv      DoorDash ORDER_DETAIL, one row per order item
    grubhub_menu_line_items.csv    Grubhub menu-line-items, one row per order item
  reference/                   <- what the restaurant must give us (APIs don't have it)
    locations.csv                  store IDs on both platforms, hours
    menu_items.csv                 menu, price, prep complexity
    prep_components.csv            things prepped ahead in batches: yield, prep time, hold time, cost, lead time
    recipes.csv                    menu item -> components (qty per item)
    modifiers.csv                  modifiers and their component adjustments
    daily_context.csv              outside signals: weather, holidays, university session, local events
  operations/                  <- our own logging (ideation doc: staffing + completion time)
    kitchen_ticket_log.csv         per order: placed, prep start, ready, handed off, staff on line
    shift_schedule.csv             line staff scheduled per location/date/hour
    daily_prep_log.csv             BASELINE prep behaviour: prepped vs used, waste, run-out hour
```

## Platform reports

**`doordash_order_detail.csv`** has the 23 documented ORDER_DETAIL fields in the documented order.
- `order_place_date` and `order_place_time` are **local** time. `created_at` is **UTC** ISO-8601. `timezone` = `America/New_York`.
- `subtotal` is the cart subtotal **repeated on every item row**. Don't sum it across rows; take it once per `dd_order_number`.
- `unit_price` includes modifier upcharges. `original_item_price` is the base menu price. There is no modifier column, matching the doc's caveat.
- `mx_order_number` and `external_order_id` are blank on about 15% of orders, since POS IDs can be null.
- `item_merchant_supplied_id` equals our `menu_item_id`. This is the join key to the recipes.

**`grubhub_menu_line_items.csv`** has the 17 documented fields, including the misspelled `fullfillment_type` (`DELIVERY` / `PICKUP`).
- `order_date` and `order_time_local` are local time. `order_time_zone` = `America/New_York`.
- `menu_item_modifiers` is a JSON string: `[{"name","id","price","quantity"}]`, or `[]`.
- `partner_order_id` is blank on about 10% of orders.

**Handling rules from the handoff doc that this data exercises:** read every ID as a string
(`dtype=str`). Count orders with *distinct order IDs*, never item rows. Sum `*_quantity` for dish
volume. Both feeds have to be unioned on location plus local hour. The two platforms have no
overlapping orders, so a union does not double-count.

## Joins

```
doordash.store_id          -> locations.doordash_store_id  -> location_key
grubhub.grubhub_store_id   -> locations.grubhub_store_id   -> location_key
doordash.item_merchant_supplied_id / grubhub.menu_item_id -> recipes.menu_item_id -> prep_components.component_id
grubhub.menu_item_modifiers[].id -> modifiers.modifier_id -> component_adjustments
kitchen_ticket_log.(source_platform, source_order_id) -> dd_order_number | grubhub order_number
daily_context.date / shift_schedule.(location_key, date, hour_local) join on local date/hour
```

**Ingredient demand for an hour** = Σ over item rows of `quantity × recipes.qty_per_item`,
plus modifier adjustments (Grubhub only). Then round up to `prep_components.batch_yield`.
Start each batch `prep_minutes_per_batch` before the hour it's needed. Don't prep more than
`hold_hours` ahead.

## Patterns built in (things the platform should rediscover)

- **Rush hours.** Lunch peaks around 12:15 and dinner around 18:30. The weekend lunch peak is later and broader, with brunch around 11. Craig has a late-night peak around 22:30 on Thu–Sat.
- **Weekday.** Fri and Sat are about 1.25× Monday's volume. Monday is the slowest day.
- **Seasonality.** Craig drops about 38% while the university is out (mid-May to Aug 23). It jumps on move-in weekend (Aug 22–23) and dips over fall break (Oct 9–11). A slight upward trend runs over the whole period.
- **Outside signals.** Rain adds about 16% and drizzle about 6%. Heat above 88°F subtracts about 6%. Holidays: July 4 runs at about 0.55×, Labor Day and Memorial Day at about 0.8×, and Halloween adds a late spike. Synthetic game days lift Strip about 1.45×, and the Strip food festival lifts it about 1.5–1.6×.
- **Item mix by daypart.** Breakfast burritos sell in the morning. Wings, queso fries, and double burgers sell late at night. Bowls sell at lunch. Strip skews toward tofu and bowls, and Craig skews toward wings and fries.
- **Staffing.** The schedule is fixed and imperfect, with a thin 3-person late crew even on Thu–Sat. `actual_prep_minutes` rises when 15-minute ticket load exceeds what the line can clear. Median prep time is about 14 minutes off-peak and 17–21 minutes at the dinner and late-night peaks.
- **Baseline prep (the problem we're solving).** `daily_prep_log` simulates a manager who preps to "same weekday two weeks ago × 1.1" in whole batches. The result is about $145–170 per day per location in waste, mostly short-hold proteins, queso, and guac. About 19% of component-days run out, mostly between 18:00 and 19:00. That gives the forecast-driven prep plan a baseline to beat: less waste and fewer run-outs.

## Known simplifications

- Sales are **not censored** when a component runs out. Orders still appear, and `qty_demand_unmet` records the shortfall. Real data would hide that lost demand, as the doc warns.
- No cancellations, adjustments, or refunds. The real versions live in separate reports (CANCELLED_ORDERS, order-adjustments).
- No scheduled or future orders. Placement time is treated as kitchen demand time. Real data should separate the two.
- DoorDash modifier usage isn't counted in the component math, because the export has no modifier column.
- Event dates, game days, and the university calendar are invented for illustration, not real 2026 schedules.
- Prices are USD decimals. Verify units on real exports.
