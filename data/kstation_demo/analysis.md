# K-Station / Tartan Express: verified synthetic rush analysis

Computed from the actual backend HTTP export and reconciled to the generated provider CSVs.
Every sale is fabricated. This is one simulated truck with two platform feeds.

October 1–31, 2026: **17,939 orders, 30,109 item lines, 33,419 item units**.

## Daily order volume and peak clock hour

Counts below combine both feeds and count orders once, rather than counting item rows.

| Date | Weekday | Type | Orders | DoorDash | Grubhub | Peak hour | Orders in peak hour |
| --- | --- | --- | ---: | ---: | ---: | --- | ---: |
| 2026-10-01 | Thursday | busy | 772 | 332 | 440 | 12:00 | 150 |
| 2026-10-02 | Friday | busy | 718 | 303 | 415 | 18:00 | 140 |
| 2026-10-03 | Saturday | busy | 783 | 325 | 458 | 18:00 | 149 |
| 2026-10-04 | Sunday | quiet | 204 | 75 | 129 | 12:00 | 74 |
| 2026-10-05 | Monday | quiet | 202 | 92 | 110 | 12:00 | 69 |
| 2026-10-06 | Tuesday | normal | 562 | 225 | 337 | 12:00 | 124 |
| 2026-10-07 | Wednesday | normal | 533 | 223 | 310 | 12:00 | 120 |
| 2026-10-08 | Thursday | busy | 756 | 320 | 436 | 12:00 | 145 |
| 2026-10-09 | Friday | busy | 714 | 273 | 441 | 18:00 | 140 |
| 2026-10-10 | Saturday | busy | 712 | 270 | 442 | 18:00 | 144 |
| 2026-10-11 | Sunday | quiet | 373 | 144 | 229 | 12:00 | 65 |
| 2026-10-12 | Monday | quiet | 383 | 151 | 232 | 12:00 | 68 |
| 2026-10-13 | Tuesday | normal | 642 | 247 | 395 | 12:00 | 115 |
| 2026-10-14 | Wednesday | normal | 565 | 235 | 330 | 12:00 | 121 |
| 2026-10-15 | Thursday | busy | 730 | 286 | 444 | 12:00 | 140 |
| 2026-10-16 | Friday | busy | 754 | 299 | 455 | 18:00 | 142 |
| 2026-10-17 | Saturday | busy | 763 | 334 | 429 | 18:00 | 148 |
| 2026-10-18 | Sunday | quiet | 366 | 143 | 223 | 12:00 | 71 |
| 2026-10-19 | Monday | quiet | 231 | 94 | 137 | 12:00 | 62 |
| 2026-10-20 | Tuesday | normal | 612 | 235 | 377 | 12:00 | 117 |
| 2026-10-21 | Wednesday | normal | 534 | 234 | 300 | 12:00 | 126 |
| 2026-10-22 | Thursday | busy | 761 | 302 | 459 | 12:00 | 148 |
| 2026-10-23 | Friday | busy | 733 | 288 | 445 | 18:00 | 145 |
| 2026-10-24 | Saturday | busy | 704 | 265 | 439 | 18:00 | 146 |
| 2026-10-25 | Sunday | quiet | 275 | 109 | 166 | 12:00 | 70 |
| 2026-10-26 | Monday | quiet | 209 | 85 | 124 | 12:00 | 67 |
| 2026-10-27 | Tuesday | normal | 555 | 239 | 316 | 12:00 | 127 |
| 2026-10-28 | Wednesday | normal | 510 | 198 | 312 | 12:00 | 124 |
| 2026-10-29 | Thursday | busy | 778 | 314 | 464 | 12:00 | 147 |
| 2026-10-30 | Friday | busy | 791 | 308 | 483 | 18:00 | 141 |
| 2026-10-31 | Saturday | busy | 714 | 278 | 436 | 18:00 | 148 |

## Recurring rushes and one isolated spike

- Lunch at 12:00 and dinner at 18:00 exceed the 15:00 shoulder on 31 of 31 days.
- All 5 Thursdays have a smaller 14:00 rush: 103.40 orders on average, versus 25.46 at 14:00 on other days.
- 2026-10-21 has 109 orders at 15:00. No other day has more than 50 orders in that clock hour; treat this as one-off evidence.
- No orders fall in the 16:00–17:00 break or outside 11:00–16:00 / 17:00–20:30.

## Busiest 15-minute windows

The full 96-bin daily curves, including zero-demand closed periods, are in analysis.json.

| Date | Start | Orders in 15 minutes |
| --- | --- | ---: |
| 2026-10-08 | 18:30 | 58 |
| 2026-10-16 | 18:30 | 56 |
| 2026-10-24 | 18:30 | 56 |
| 2026-10-09 | 18:30 | 54 |
| 2026-10-17 | 12:30 | 54 |
| 2026-10-29 | 18:30 | 54 |
| 2026-10-01 | 18:30 | 53 |
| 2026-10-10 | 18:30 | 53 |

## Changing dish mix

Shares compare October 1–7 with October 25–31, rather than confusing growing volume with changing mix.

| Configured demo item | First-week unit share | Last-week unit share | Change (pp) |
| --- | ---: | ---: | ---: |
| Bulgogi Beef Rice Bowl | 8.13% | 7.96% | -0.17 |
| Bulgogi Beef Salad Bowl | 6.88% | 6.42% | -0.46 |
| Ginger Salad | 1.36% | 1.51% | +0.15 |
| K-Signature Bowl | 5.83% | 6.21% | +0.38 |
| Kimchi (4 oz) | 1.85% | 1.65% | -0.20 |
| Korean BBQ Chicken Rice Bowl | 5.38% | 6.07% | +0.69 |
| Mandoo (6 pieces) | 2.56% | 2.12% | -0.45 |
| Mandoo Rice Bowl | 2.92% | 2.79% | -0.13 |
| OG Gochujang Chicken Rice Bowl | 7.97% | 7.44% | -0.53 |
| OG Gochujang Chicken Salad Bowl | 7.21% | 6.42% | -0.79 |
| Pepsi Can | 4.26% | 4.44% | +0.18 |
| Side Fries | 2.66% | 2.44% | -0.22 |
| Side Rice | 0.93% | 1.18% | +0.24 |
| Spicy BBQ Pork Belly Rice Bowl | 3.99% | 19.68% | +15.69 |
| Spicy BBQ Pork Belly Salad Bowl | 6.40% | 6.35% | -0.05 |
| Strawberry Ade Pouch | 2.52% | 2.37% | -0.15 |
| Tangy Fried Chicken Rice Bowl | 17.54% | 3.57% | -13.97 |
| Tangy Fried Chicken Salad Bowl | 6.07% | 6.03% | -0.05 |
| The Original Kimchi Fries | 5.51% | 5.34% | -0.17 |

## Lunch versus dinner preferences

The three largest item-unit shares within each service window:

- Lunch: Spicy BBQ Pork Belly Rice Bowl (16.50%); Tangy Fried Chicken Rice Bowl (14.89%); Bulgogi Beef Rice Bowl (11.88%)
- Dinner: OG Gochujang Chicken Salad Bowl (11.85%); Bulgogi Beef Salad Bowl (11.54%); Spicy BBQ Pork Belly Salad Bowl (10.77%)

## Verification

- All exported file hashes and row counts match the export manifest.
- Every original CSV row is preserved exactly in exported source details.
- Store-scoped order IDs, quantities, prices, local times and modifiers reconcile.
- All records carrying a synthetic flag are synthetic; imports succeeded.
- Observed platform item identities reconcile without inventing canonical mappings.
- Source report hashes, all daily ranges, peak-hour ranges, and 15-minute totals pass.

## Limitations

- Fabricated scenario inspired by a public campus menu; not K-Station sales evidence.
- Both sources are simulated. No actual provider accounts or listings were verified.
- Clock-hour and 15-minute figures count distinct orders across both feeds, not lines.
- October supplies four or five instances of each weekday, fewer than eight baseline weeks.
- No preparation capacity, queue/wait time, ingredient stock, or stockout inference is supported.
- The isolated spike has no invented cause; repeated patterns are descriptive, not causal.
- Item display names are deliberately configured demo variants, not verified marketplace SKUs.
