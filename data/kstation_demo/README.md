# K-Station / Tartan Express: synthetic October rush demo

This fabricated scenario represents **one campus food truck** with two simulated sales feeds. The concept is K-Station; Tartan Express is the user-reported Grubhub name. Neither the listing name nor participation on both platforms has been verified through a provider account.

**October 1–31, 2026: 17,939 orders, 30,109 item lines, and 33,419 item units.** Every order and demand pattern is synthetic. Menu inspiration comes from CMU's campus menu, not private restaurant records or the Schenley Plaza location's menu.

## What the demo can show

Counts combine DoorDash and Grubhub and count each order once, rather than counting item rows.

| Day type | Designed daily range | Designed busiest clock hour | Example from the generated data |
| --- | --- | --- | --- |
| Quiet: Sunday/Monday | 200–400 orders | 40–75 orders | October 4: 204 orders; peak 74 |
| Normal: Tuesday/Wednesday | 500–650 orders | 100–130 orders | October 6: 562 orders; peak 124 |
| Busy: Thursday–Saturday | 700–800 orders | 140–150 orders | October 1: 772 orders; peak 150 |

- Lunch around noon and dinner around 6 PM recur across the month.
- All five Thursdays have an additional 2 PM rush: **103.4 orders on average**, versus 25.46 at 2 PM on other days.
- October 21 has a **single 3 PM spike of 109 orders**. No cause is invented, and no other day exceeds 50 orders in that hour.
- Spicy BBQ Pork Belly Rice Bowl grows from **3.99% to 19.68%** of item units between the first and last seven days. Tangy Fried Chicken Rice Bowl declines from **17.54% to 3.57%**.
- Rice bowls are more prominent at lunch; salad bowls are more prominent at dinner.

See [analysis.md](analysis.md) for measured daily totals, peak hours, quarter-hour examples, and item trends. [analysis.json](analysis.json) contains all 31 daily 96-bin curves, including closed periods with zero orders. Values describe this designed scenario; they do not prove real demand or business impact.

## Menu and pricing attribution

The source is [CMU's K-Station campus menu PDF](https://apps.studentaffairs.cmu.edu/dining/dashboard_images/Production/menus/206/KS%2010.1.pdf), visually inspected November 7, 2026. It includes build-your-own rice/salad bowls, protein choices, the K-Signature Bowl, original kimchi fries, sides, and drinks. A publicly readable campus Grubhub menu was not obtained. No historical October menu/prices were verified.

The scenario uses 19 synthetic configured listings. For example, "Bulgogi Beef Rice Bowl" flattens a base/protein choice into a demo item; it is not a verified marketplace SKU. Lunch bowl bases use $14 and dinner bases $16, with the menu-inspired $1 beef premium. Signature items, sides, drinks, and add-on assumptions are listed explicitly in `manifest.json`.

For this simulation, lunch pricing applies during 11 AM–4 PM; dinner pricing starts at 5 PM. DoorDash unit prices include the simulated add-on charges, while Grubhub has base prices and modifier arrays. These are explicit demo conventions, not guarantees about real provider pricing semantics. DoorDash modifiers are not invented as a report column, and Grubhub order subtotals remain unknown in the normalized records.

Operating windows are **11 AM–4 PM and 5–8:30 PM every day**. These are scenario assumptions based on [CMU's published dining listing](https://apps.studentaffairs.cmu.edu/dining/conceptinfo), not verified historical October hours. There are no sales during the break or after closing.

## Files and mappings

| File or directory | Contents |
| --- | --- |
| `platform_reports/` | Generated CSVs matching the current 23-column DoorDash and 17-column Grubhub import formats |
| `manifest.json` | Seed, hashes, expected daily/hourly/quarter-hour counts, source counts, menu mappings, attribution, and assumptions |
| `backend_export/` | Actual paginated HTTP exports of the five sales collections, compressed as JSON Lines |
| `backend_export/export_manifest.json` | Exported collection counts, checksums, and total quantities |
| `analysis.md`, `analysis.json` | Independent reconciliation and observed demand analysis |
| `preservation.json` | Results of local replay and existing-record/file preservation checks |

| Feed | External store ID | Orders | Item lines | Item units |
| --- | --- | ---: | ---: | ---: |
| DoorDash | `9900201` | 7,226 | 12,100 | 13,422 |
| Grubhub | `8800201` | 10,713 | 18,009 | 19,997 |

Both platform records deliberately represent this one synthetic truck; the backend itself does not automatically infer or merge restaurant identity. The manifest's menu entries map each synthetic canonical ID to its DoorDash and Grubhub IDs. There are no recipe quantities behind these mappings.

Find internal store UUIDs through `GET /stores`, then use those UUIDs in the `store_id` filter on `/orders`, `/order-lines`, or `/items`. Query both selected stores to calculate truck-wide demand. A platform filter alone includes other demo restaurants already in the database; use store filters or the supplied cohort export to avoid mixing scenarios.

## Reproduce the pipeline

Run from this worktree's `backend/` directory. The [backend guide](../../backend/README.md) covers Docker startup and migrations. The live local backend already contains this scenario; these commands can recreate it on another local setup. Build the image to include the new tools:

```sh
docker compose build
docker compose run --rm migrate
docker compose up -d api
docker compose run --rm api python -m nova_backend.imports --source doordash --file /workspace/data/kstation_demo/platform_reports/doordash_order_detail.csv --synthetic --complete-orders
docker compose run --rm api python -m nova_backend.imports --source grubhub --file /workspace/data/kstation_demo/platform_reports/grubhub_menu_line_items.csv --synthetic --complete-orders
```

Both reports contain complete orders. Reimporting the same reports preserves internal order IDs and does not duplicate sales. Internal item-line IDs can change when their complete order is refreshed. Other stores are left untouched.

To export current records to a new directory, use an explicit writable scenario mount; the normal repository mount is read-only:

```sh
docker compose run --rm -v "$PWD/../data/kstation_demo:/scenario" api python -m nova_backend.export --base-url http://api:8000 --store doordash:9900201 --store grubhub:8800201 --out /scenario/backend_export_new
```

The tool refuses to overwrite existing exports, follows every pagination cursor, includes only the selected stores and referenced imports, and checks for order/import changes during the read. Pause imports while exporting; this is not a transaction snapshot across HTTP requests.

Regenerate source reports into a separate empty directory without overwriting the provided artifacts:

```sh
docker compose run --rm -v "$PWD/../data:/datasets" api python -m nova_backend.kstation --out /datasets/kstation_demo_regenerated --seed 20261107
```

The same seed and generator version produce identical source files and manifests. Different seeds reuse this scenario's store-ID namespace; use another database or distinct store IDs for alternative variants rather than mixing them with these records.

To recheck the provided API export and run the suite:

```sh
docker compose run --rm -v "$PWD/../data/kstation_demo:/workspace/data/kstation_demo" api python scripts/analyze_kstation.py --dataset /workspace/data/kstation_demo
docker compose --profile test run --rm test
docker compose run --rm api ruff check .
docker compose run --rm api ruff format --check .
```

The analyzer uses source CSVs and API-exported records, independently recalculating actual order counts, hourly/quarter-hour distributions, and item shares. It verifies source/export checksums and row reconciliation before writing its analysis. The writable mount above allows the analysis artifacts to be refreshed. Tests use the separate disposable PostgreSQL test database.

## Verified limits

Only sales/report fields are present. No recipes, inventory, preparation durations, staffing, kitchen logs, weather, or event causes are supplied or inferred. The data cannot establish capacity, waiting times, lost demand, or stockouts. Login, OAuth, real provider downloads, and scheduled synchronization are not implemented by this scenario.

October supplies four or five occurrences of each weekday, fewer than David's eight-week baseline. Historical forecasts must use only earlier dates, report the actual comparable-day count, and make insufficient-history confidence explicit. The integration branch connects this dataset to the sales-only tablet through `/tablet` and `/tablet/outlook`; see [the demo guide](../../docs/local-demo.md). The legacy recipe agent is not used.

All source reports, backend exports, and analysis outputs are labeled synthetic. Existing Harbor Deli files, prior database rows, and prior import audit records were preserved during initial imports and replay. Nothing in this folder constitutes K-Station's real sales evidence.
