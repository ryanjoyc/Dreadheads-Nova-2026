# Synthetic sales demo: verified example analysis

All figures below are calculated from the actual backend API export, after reconciliation to the two generated provider reports.
This is fabricated sales data for demonstration. Designed patterns are not evidence of real demand, stockouts, or business outcomes.

Coverage: 2026-05-01–2026-10-31 (184 calendar days).
Totals: 4 platform stores, 45,000 orders, 85,651 item lines, 99,440 units.

## Weekday demand

Compare daily averages rather than raw totals, because the range contains different numbers of each weekday.

| Weekday | Calendar days | Orders | Orders/day |
| --- | ---: | ---: | ---: |
| Monday | 26 | 6,324 | 243.23 |
| Tuesday | 26 | 6,362 | 244.69 |
| Wednesday | 26 | 6,563 | 252.42 |
| Thursday | 26 | 6,281 | 241.58 |
| Friday | 27 | 6,544 | 242.37 |
| Saturday | 27 | 6,639 | 245.89 |
| Sunday | 26 | 6,287 | 241.81 |

## Monthly platform and fulfillment trends

| Month | Orders/day | Grubhub order share | Delivery order share |
| --- | ---: | ---: | ---: |
| 2026-05 | 209.61 | 26.92% | 77.13% |
| 2026-06 | 223.63 | 34.60% | 76.46% |
| 2026-07 | 235.58 | 42.61% | 75.67% |
| 2026-08 | 257.52 | 50.12% | 75.69% |
| 2026-09 | 265.53 | 58.08% | 75.30% |
| 2026-10 | 275.52 | 66.40% | 76.20% |

## Store/platform demand

These rows preserve each platform's store identity. Repeated display names do not create a canonical restaurant mapping.

| Store | Platform | Orders/day | Three busiest clock hours |
| --- | --- | ---: | --- |
| Harbor Deli - Market (SYNTHETIC) | doordash | 71.87 | 13:00 (2,715 orders), 11:00 (2,679 orders), 12:00 (2,645 orders) |
| Harbor Deli - Market (SYNTHETIC) | grubhub | 55.92 | 12:00 (2,061 orders), 11:00 (2,047 orders), 13:00 (2,011 orders) |
| Harbor Deli - Uptown (SYNTHETIC) | doordash | 55.95 | 17:00 (1,158 orders), 19:00 (1,148 orders), 21:00 (1,132 orders) |
| Harbor Deli - Uptown (SYNTHETIC) | grubhub | 60.82 | 19:00 (1,292 orders), 20:00 (1,251 orders), 18:00 (1,228 orders) |

## Changing item mix

Compare each display name's share of item units in the first and last months. These are observed sales shares, not causal explanations.

| Item display name | First month share | Last month share | Change (percentage points) |
| --- | ---: | ---: | ---: |
| Breakfast Bagel | 3.27% | 2.98% | -0.29 |
| Chicken Wrap | 8.98% | 8.52% | -0.46 |
| Chocolate Cookie | 5.30% | 5.35% | +0.05 |
| Citrus Grain Bowl | 3.43% | 20.78% | +17.35 |
| Coffee | 2.74% | 2.46% | -0.28 |
| Crispy Fries | 9.21% | 8.90% | -0.31 |
| Fruit Cup | 4.07% | 4.14% | +0.07 |
| Garden Salad | 7.06% | 6.37% | -0.69 |
| Iced Tea | 6.28% | 6.11% | -0.17 |
| Roast Beef Sandwich | 19.43% | 5.04% | -14.39 |
| Spicy Chicken Sandwich | 8.37% | 8.02% | -0.35 |
| Tomato Soup | 3.94% | 3.95% | +0.01 |
| Turkey Club | 9.83% | 9.48% | -0.35 |
| Veggie Wrap | 5.71% | 5.73% | +0.02 |
| Weekend Pancakes | 2.37% | 2.19% | -0.18 |

## Reconciliation

- All exported file hashes and row counts match the export manifest.
- Every original CSV row is preserved exactly in exported source details.
- Store-scoped order IDs, quantities, prices, local times and modifiers reconcile.
- All records carrying a synthetic flag are synthetic; imports succeeded.
- Observed platform item identities reconcile without inventing canonical mappings.

## Boundaries

- Synthetic designed patterns support demos, not real-world accuracy claims.
- Calendar-day rates include all dates in the observed range; they do not establish store opening hours or report completeness.
- Item display-name grouping is an analysis convenience, not an approved cross-platform identity mapping.
- No recipe, inventory, stockout, staffing, weather, or event evidence is present.

For additional examples, use `analysis.json` for all monthly item shares, platform-store hourly counts, and weekday daily averages.
