# Harbor Deli: sales-only synthetic demo

This is a separate fabricated scenario, generated at roughly the scale of Morningjoe's original sample. It simulates the report files available after authorized restaurant access to DoorDash and Grubhub. No accounts were connected, no credentials were used, and no real provider requests were made.

**45,000 orders, 85,651 item lines, 99,440 item units**, May 1–October 31, 2026. Fifteen item labels appear at two fictional locations, Market and Uptown. Each location has a separate store identity on each platform.

The data is loaded in the existing local sales backend. Existing sample records were preserved: the backend has 45,012 total orders when including the original twelve fixtures. Filter to this scenario's stores to reproduce the counts above.

## Files

| File or directory | Contents |
| --- | --- |
| `platform_reports/` | Generated DoorDash `ORDER_DETAIL` and Grubhub `menu-line-items` CSVs, using the exact 23/17 columns accepted by our current importers |
| `manifest.json` | Reproducible seed, source counts, IDs, date ranges, SHA-256 hashes, designed patterns, and assumptions |
| `backend_export/` | Actual paginated HTTP exports from `/stores`, `/orders`, `/order-lines`, `/items`, and `/imports`, compressed as JSON Lines |
| `backend_export/export_manifest.json` | Store selection, collection counts, compressed-file hashes, and total quantities |
| `analysis.md` | Readable example analysis, computed from the actual backend export after source reconciliation |
| `analysis.json` | Detailed monthly, weekday, hourly, and item metrics for analytics teammates |

The JSON Lines exports preserve API records, including original row values in line `source_details`. Compression changes file storage, not field contents. Backend UUIDs and import timestamps describe the actual local import; those values are not deterministic across different databases. Source reports are deterministic for the same seed, count, and generator version.

There are no recipe, inventory, waste, staffing, kitchen-log, weather, or event files. Those facts cannot be inferred from this sales dataset. The original Morningjoe dataset is unchanged.

## Example analyses

See [analysis.md](analysis.md) for verified values. Examples include:

- Growing order volume: 209.61 orders/day in May versus 275.52 in October.
- Changing channel mix: Grubhub order share increases from 26.92% to 66.40%.
- Growing dish: Citrus Grain Bowl increases from 3.43% to 20.78% of item units.
- Declining dish: Roast Beef Sandwich decreases from 19.43% to 5.04% of item units.
- Different rush patterns: Market concentrates around lunch; Uptown around dinner.
- Location-specific weekday/weekend patterns, breakfast item demand, and pickup-versus-delivery patterns are available in the detailed metrics.

These patterns are deliberately generated. They can demonstrate an analysis workflow but cannot establish forecast accuracy or real-world business impact. Item-name grouping is a demo analysis convenience, not a verified cross-platform dish mapping. Calendar-day rates do not establish opening hours or report completeness.

## Scenario store identities

| Synthetic location | DoorDash store ID | Grubhub store ID |
| --- | --- | --- |
| Uptown | `9900101` | `8800101` |
| Market | `9900102` | `8800102` |

`GET /stores` supplies each platform store's internal UUID. Use that UUID in the sales API's `store_id` filter. The backend retains four separate platform-store records. The generator explicitly designed the two-location pairing above; the backend did not discover or merge it.

## Run through the existing backend

From this worktree's `backend/` directory, follow [the backend setup](../../backend/README.md) if the API is not running. Build the image to include the new generator/export tools:

```sh
docker compose build
docker compose run --rm migrate
docker compose up -d api
docker compose run --rm api python -m nova_backend.imports --source doordash --file /workspace/data/sales_only_demo/platform_reports/doordash_order_detail.csv --synthetic --complete-orders
docker compose run --rm api python -m nova_backend.imports --source grubhub --file /workspace/data/sales_only_demo/platform_reports/grubhub_menu_line_items.csv --synthetic --complete-orders
```

Both files contain complete orders. Imports preserve other stores, and importing the same files again updates this cohort without duplicating sales. Optional POS identifiers are sometimes blank. Repeated dishes remain separate lines. Dollar-price and modifier conventions are stated in `manifest.json`; they still need checking against actual provider exports before real merchant use.

### Export current records

The provided export directory is an artifact of this local verification run. To make another export, choose a fresh directory; the exporter refuses to overwrite files:

```sh
docker compose run --rm api python -m nova_backend.export --base-url http://api:8000 --store doordash:9900101 --store doordash:9900102 --store grubhub:8800101 --store grubhub:8800102 --out /workspace/data/sales_only_demo/backend_export_new
```

This follows every pagination cursor and includes only selected stores and their referenced imports. Do not import corrections concurrently with an export. The tool compares order/import revisions before and after reading and refuses a changed dataset, but does not create a database transaction snapshot across HTTP requests. It is limited to local synthetic-data exports.

Read an exported collection with standard Python:

```python
import gzip
import json

with gzip.open("backend_export/order_lines.jsonl.gz", "rt") as stream:
    for line in stream:
        record = json.loads(line)
        # record contains the same fields returned by GET /order-lines.
```

## Regenerate and verify

Generate a new copy in an empty directory, leaving the provided data untouched:

```sh
docker compose run --rm api python -m nova_backend.synthetic --out /workspace/data/sales_only_demo_regenerated --orders 45000 --seed 20261107
docker compose run --rm api python scripts/analyze_sales_demo.py --dataset /workspace/data/sales_only_demo
docker compose --profile test run --rm test
```

The independent analyzer compares source CSV cells with exported original rows, checks normalized order/item identities, quantities, prices, times, modifiers, provenance, and file hashes, then calculates trends. It does not reuse the generator or importer to construct expected totals.

Use the default seed and count to reproduce these exact source files. Different seeds/counts reuse this scenario's store-ID namespace and should be imported into a separate database or assigned distinct store identities first; mixing variants is not supported. Real account login, OAuth, scheduled downloads, and live order integrations remain outside this implementation.
