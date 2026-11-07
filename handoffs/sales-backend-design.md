# Sales-only backend design

Prepared November 7, 2026. Audience: backend and analytics teammates.

Status: proposed design, not an implemented backend. Credentials and real merchant reports have not been obtained or tested.

## Purpose

Store normalized sales records from DoorDash `ORDER_DETAIL` and Grubhub `menu-line-items` in PostgreSQL. Give teammates read-only JSON endpoints for retrieving those records. Import historical reports initially, then refresh on each provider's reporting schedule.

This version uses documented report fields plus internal IDs and import bookkeeping. It does not include inventory, recipes, forecasts, ingredient calculations, live orders, or David's recommendation calculations. It provides data those features may consume later; it does not replace the proposed [recommendations spec](recommendations-spec.md).

All example records are synthetic. Verify actual report formats before connecting real merchants. See the [API field handoff](restaurant-api-data-handoff.md) for field availability and access constraints.

## Tables

| Table | One row represents | Starting fields |
| --- | --- | --- |
| `source_stores` | One store on one platform | `id`, `source`, `external_store_id`, `store_name`, `timezone`, `source_details` |
| `orders` | One platform order | `id`, `source_store_id`, `external_order_id`, `order_number`, `placed_at_local`, `source_timezone`, `fulfillment`, `subtotal`, `source_details`, `last_import_run_id` |
| `order_lines` | One item line within an order | `id`, `order_id`, `external_line_id`, `external_item_id`, `item_name`, `category_name`, `quantity`, `unit_price`, `modifiers`, `source_details` |
| `import_runs` | One report import attempt | `id`, `source`, `report_type`, `report_version`, `requested_columns`, `date_start`, `date_end`, `provider_report_id`, `status`, `started_at`, `completed_at`, `raw_file_reference`, `is_synthetic`, `error` |

Use internal IDs for relationships and text for external identifiers. Store quantities and prices with exact numeric types; validate price units before normalization. Fields unavailable from a source remain null. `source_details` is JSONB for additional parsed provider fields. `modifiers` can hold parsed Grubhub modifier data after its encoding is verified.

```text
source_stores
      |
      +-- orders
              |
              +-- order_lines

orders.last_import_run_id --> import_runs.id
```

Preserve original downloaded files separately and reference them from `import_runs`. Store report versions, selected columns, and requested date coverage so an import can be traced and reproduced. Requested coverage does not by itself prove that every date has complete data.

Store timezone information alongside the source-local timestamp. Derive an absolute timestamp only when the source's timezone and timestamp semantics are confirmed; do not silently guess during daylight-saving transitions. Preserve historical item names and prices on order lines.

### Combining sources

Both platforms use the same tables and field names. Every order retains its source through `source_store_id`.

This normalization does not establish that two platform stores are the same physical restaurant, or that similarly named items are the same dish. Keep platform identities separate until a mapping is confirmed. A later approved location/menu mapping can support combined restaurant and dish totals without changing the original records. It is not inferred from the reports in this version.

## Provider mappings

| Shared field | DoorDash `ORDER_DETAIL` | Grubhub `menu-line-items` |
| --- | --- | --- |
| `source` | Internal constant: `doordash` | Internal constant: `grubhub` |
| External store ID | `store_id` | `grubhub_store_id` |
| Store name | `store_name` | `store_name` |
| External order identity | `dd_order_number` | Prefer `order_uuid`; retain `order_number` separately |
| Placement time | `order_place_date` + `order_place_time` | `order_date` + `order_time_local` |
| Timezone | `timezone` | `order_time_zone` |
| External item-line ID | `order_item_id` | Not documented in the reviewed dictionary |
| External item ID | `dd_item_id` | `menu_item_id` |
| Item name | `item_name` | `menu_item_name` |
| Category | `category_name` | `menu_item_category_name` |
| Quantity | `order_item_quantity` | `menu_item_quantity` |
| Unit price | `unit_price` | `menu_item_price` |
| Order subtotal | `subtotal` | Not supplied by the reviewed item report |
| Fulfillment | Normalize `is_consumer_pickup` | Normalize `fullfillment_type` |
| Modifiers | Unconfirmed; null initially | `menu_item_modifiers` |

DoorDash placement fields require report version 2 or later. Preserve its business, merchant-supplied item, POS, and other identifiers in `source_details`; do the same for Grubhub's additional identifiers. Do not assume IDs from different report types are interchangeable.

Validate timestamp interpretation, monetary units, fulfillment values, identifier availability, and modifier serialization against actual exports before enabling real imports. Missing identifiers must be surfaced as an import validation issue rather than replaced with an invented provider ID.

Sources: [DoorDash Order Details dictionary](https://developer.doordash.com/en-US/docs/reporting/overview/reports/marketplace_merchant_pick/#order-details), [Grubhub Menu Line Items dictionary](https://developer.grubhub.com/docs/6MHHprfOgKrUADOOePCFPE/available-reports#menu-line-items-available-fields). Field inventory documented in the API handoff on November 7, 2026.

## Starting endpoints

These are our backend endpoints, not DoorDash or Grubhub endpoints. They read previously imported records; a request does not trigger a provider download.

| Endpoint | Returns |
| --- | --- |
| `GET /stores` | Observed platform stores and their internal IDs |
| `GET /orders` | Order-level records filtered by store, platform, and placement date |
| `GET /order-lines` | Flattened sales records joining source, store, order, placement time, and item fields |
| `GET /items` | Distinct observed platform item IDs and their latest observed labels; not a complete current menu |
| `GET /imports` | Import status, requested coverage, completion time, and synthetic-data labels |

Collection responses use `data` and `next_cursor`. Accept an opaque `cursor` and a `limit` defaulting to 100, capped at 500, with deterministic ordering. Unknown stores return an empty collection; malformed filters return HTTP 400.

`/orders` and `/order-lines` accept optional `source`, `store_id`, `date_start`, and `date_end`. `store_id` is our internal source-store ID. Date filters use the store-local placement date, with an inclusive start and exclusive end. `/items` and `/stores` accept a source filter; `/items` also accepts a store filter. `/imports` accepts source and status filters. Import request coverage follows the provider's date-boundary rules and must be translated separately from our API filters.

The `/order-lines` response is the shared analytics dataset. It can return both sources, while retaining separate platform store and item identities. Monetary values are decimal strings or null, not binary floating-point values. Each record carries `is_synthetic` from its import provenance. Orders and lines also expose their last import reference so consumers can inspect freshness via `/imports`; import time is not the same as the provider's data cutoff.

### Synthetic response example

`GET /order-lines?source=doordash&date_start=2026-11-06&date_end=2026-11-07`

```json
{
  "data": [
    {
      "source": "doordash",
      "store_id": "store-dd-1",
      "external_store_id": "123",
      "order_id": "order-1",
      "external_order_id": "DD-101",
      "placed_at_local": "2026-11-06T12:15:00",
      "timezone": "America/New_York",
      "external_item_id": "item-456",
      "item_name": "Classic Burger",
      "quantity": 2,
      "unit_price": "12.50",
      "fulfillment": "delivery",
      "modifiers": null,
      "last_import_run_id": "import-demo-1",
      "is_synthetic": true
    }
  ],
  "next_cursor": null
}
```

This is an example of our normalized response, not a native provider response or evidence of retrieved merchant data.

## Import behavior

- Request reports, wait for completion, download the source files, validate them, then persist normalized records. Reporting APIs return job metadata before the CSV records are available.
- Scope order identity to its source store. Enforce uniqueness on `(source, external_store_id)` for stores and `(source_store_id, external_order_id)` for orders.
- Refresh recent history to capture provider corrections. Reimporting overlapping reports must not duplicate orders or item quantities.
- Preserve multiple lines for the same dish, including different modifiers. Do not deduplicate by item ID alone.
- DoorDash supplies an item-line identifier. Grubhub's reviewed dictionary does not. Before importing Grubhub into persistent tables, verify that the requested report includes complete line sets for included orders. If verified, transactionally replace each included order's line set. If not verified, stop and resolve the reconciliation contract rather than applying an unsafe deduplication rule.
- Do not delete orders merely because they are absent from a later report. Absence does not establish cancellation or deletion.
- Keep order subtotal on `orders`; never sum it across repeated item rows. Do not derive a Grubhub subtotal by assuming quantity times item price includes modifiers, discounts, or other charges.
- Preserve synthetic labels through storage and API responses. Never silently mix synthetic records with real merchant data under the same source-store identity.
- These reports describe observed orders and item quantities. They do not alone establish fulfillment completion, true unconstrained demand, ingredient stock, or preparation duration.

Real provider credentials remain server-side. Frontend clients use our API rather than database credentials. Authentication and restaurant authorization must be defined before exposing real merchant data; this document does not specify a public deployment.

## Acceptance checks for a future implementation

1. Import labeled fixtures from both providers and verify the mapped IDs, names, quantities, placement times, and source provenance.
2. Reimport the same and overlapping fixtures; order counts and item quantities remain unchanged unless source values changed.
3. Import an order containing the same dish on multiple lines; preserve every line and modifier distinction.
4. Give both platforms the same external order/item identifiers; records remain separate.
5. Verify store/source/date filters, pagination without skipped or repeated rows, and null values for unavailable fields.
6. Verify local dates around midnight and timezone transitions; unresolved timestamps are flagged rather than guessed.
7. Count distinct internal orders for order volume and sum line quantities for dish volume; repeated subtotals do not inflate totals.
8. Verify import failure reporting, traceability to original files, and synthetic labels on returned records.

## Deliverable boundary

This document is a blueprint. It does not create a server, database migration, running endpoint, provider integration, or recommendation algorithm. Teammate ownership and the integration contract with analytics remain to be agreed.
