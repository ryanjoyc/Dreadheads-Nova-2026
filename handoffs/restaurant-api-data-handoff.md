# Restaurant API data handoff

Prepared November 7, 2026. Audience: analytics teammates.

## DoorDash historical fields

Report type: `ORDER_DETAIL`, in Marketplace Merchant Pick reporting for restaurants.

| Information | Exact documented fields |
| --- | --- |
| Business/location | `business_id`, `store_id`, `business_name`, `store_name` |
| Order identifier | `dd_order_number` |
| Placement date/time | `order_place_date`, `order_place_time`, `created_at` |
| Restaurant timezone | `timezone` |
| Item identifiers | `dd_item_id`, `item_merchant_supplied_id`, `order_item_id` |
| Item labels | `item_name`, `category_name`, `menu_name` |
| Quantity | `order_item_quantity` |
| Item prices | `unit_price`, `original_item_price` |
| Cart subtotal | `subtotal` |
| Customer pickup | `is_consumer_pickup` |
| DashPass eligibility | `dashpass` |
| POS identifiers | `mx_order_number`, `external_order_id` |

Placement date/time fields above were added in report version 2. POS identifiers can be null. The report description mentions modifiers, but its displayed dictionary does not specify a modifier column; confirm the actual export before relying on one. Some published type labels/examples are inconsistent, so validate types and timestamp conventions against retrieved files.

[Source: DoorDash Order Details dictionary](https://developer.doordash.com/en-US/docs/reporting/overview/reports/marketplace_merchant_pick/#order-details)

## Grubhub historical fields

Report type: `menu-line-items`.

| Information | Exact documented fields |
| --- | --- |
| Location | `grubhub_store_id`, `store_name`, `store_number`, `external_id` |
| Order identifiers | `order_number`, `order_uuid`, `partner_order_id` |
| Placement date/time | `order_date`, `order_time_local` |
| Restaurant timezone | `order_time_zone` |
| Item identifier | `menu_item_id` |
| Item labels | `menu_item_name`, `menu_item_category_name` |
| Quantity | `menu_item_quantity` |
| Item price | `menu_item_price` |
| Modifiers | `menu_item_modifiers` |
| Fulfillment method | `fullfillment_type` |

`fullfillment_type` preserves the spelling in the published dictionary. Modifiers contain names, IDs, prices, and quantities; inspect their encoding in the CSV before parsing. `partner_order_id` is not available in real time. Store ID and order number are required columns for this report.

[Source: Grubhub Menu Line Items dictionary](https://developer.grubhub.com/docs/6MHHprfOgKrUADOOePCFPE/available-reports#menu-line-items-available-fields)

## What we can build against

DoorDash and Grubhub document restaurant reports containing **order times, menu items, and quantities**. These are the core inputs for forecasting dish demand by hour and weekday.

**Status: documentation verified; credentials, merchant authorization, and actual restaurant records have not been obtained or tested.** The fields below describe the provider schemas, not data already in our possession. Individual values may be missing. This is a focused field reference, not an exhaustive inventory of every API.

## What format do the APIs return?

JSON is structured data with named fields and nested objects. CSV is a table stored as text, with a header and rows. Reporting involves both: JSON controls the report job; a separate downloaded file contains the records.

| Integration | Immediate API response or event | Analytics data |
| --- | --- | --- |
| DoorDash Reporting | JSON report ID, followed by JSON status/download link | ZIP containing CSV |
| Grubhub Reporting | JSON report UUID, followed by JSON download URL | Generated CSV report |
| Marketplace live orders on either platform | Webhook sends a JSON order/event body to our server | Nested order data that we flatten into tables |

The reporting API does **not** immediately return a JSON array of historical orders.

### DoorDash report workflow

1. Send a JSON request to `POST https://openapi.doordash.com/dataexchange/v1/reports` specifying report type, dates, and authorized locations.
2. Receive a JSON response containing `report_id`.
3. Wait for report completion using the report-ready webhook or the documented polling flow.
4. Request `GET https://openapi.doordash.com/dataexchange/v1/reports/{report_id}/reportlink`.
5. Read `report_status` and `report_link`; download the ZIP and extract the CSV when ready.

Report-ready notifications mean the requested export is generated; they do not mean a customer just placed an order. [DoorDash report workflow](https://developer.doordash.com/en-US/docs/reporting/how_to/get_a_report/)

### Grubhub report workflow

1. Send JSON to `POST /merchant/reporting/v1/reports`, including `report_type`, `report_columns`, `merchant_ids`, and `report_parameters` with a date range.
2. Receive JSON containing `report_uuid`.
3. Handle the report-status webhook, including complete, error, and no-data outcomes.
4. Request `GET /merchant/reporting/v1/reports/{reportUuid}` to obtain JSON containing `download_url`.
5. Download the CSV from that URL.

Grubhub allows selecting report columns. Request the fields the analytics team needs rather than assuming every available column is automatically included. [Reporting endpoint schemas](https://developer.grubhub.com/api/reporting-endpoints), [workflow](https://developer.grubhub.com/docs/6AWV4VW2XFayLI9SYrzugm/reporting-api-overview)

For illustration only, the metadata responses look like this; these IDs and URLs are synthetic:

```json
{"report_id": "example-doordash-report-id"}
```

```json
{"report_uuid": "example-grubhub-report-uuid"}
```

Neither response contains sales rows yet.

## Other information available through separate reports

| Area | DoorDash | Grubhub |
| --- | --- | --- |
| Cancellations | `CANCELLED_ORDERS` | `cancellations` |
| Fulfillment performance | `AVOIDABLE_WAIT` | `order-details`, `operations-summary` |
| Item performance/errors | `MENU_ITEM_ERROR` | `product-mix`, `order-adjustments` |
| Financials | `TRANSACTION_DETAIL`, `PAYOUT_SUMMARY` | `transactions`, `deposits`, `financials-summary` |

Pull and join these separately if needed. Their row meanings and identifiers differ. A report of item errors is not a complete sales ledger.

Sources: [DoorDash reports](https://developer.doordash.com/en-US/docs/reporting/overview/available_reports/), [Grubhub reports](https://developer.grubhub.com/docs/6MHHprfOgKrUADOOePCFPE/available-reports).

## What analytics can derive

The following are calculations our team builds, rather than precomputed fields promised by the APIs:

- Item quantities sold by local hour and weekday.
- Order counts and peaks, using distinct order IDs rather than counting item rows.
- Item mix, trends, and forecasts for a future service period.
- Preparation recommendations using explicit assumptions about capacity and batch sizes.

Ingredient purchasing needs **recipes, portion quantities, stock counts, waste, and supplier lead times** from another source. Sales alone do not reveal actual inventory or unconstrained demand when items sell out.

## Access and freshness

| Source | Documented limits |
| --- | --- |
| DoorDash Reporting | Limited approved access; token mapped to stores/businesses; daily refresh; up to two years of history |
| Grubhub Reporting | Authorized/onboarded merchant IDs and HMAC authentication; contact a representative; potential 1–2 day lag; maximum one year per request |
| Marketplace live orders | Partner credentials and integration setup; JSON webhooks; production requirements apply |

The Grubhub one-year limit is a request span, not a universal retention limit. Neither API grants access to arbitrary restaurants or automatically supplies realistic demo history.

Sources: [DoorDash access](https://developer.doordash.com/en-US/docs/reporting/how_to/get_access/), [DoorDash freshness/history](https://developer.doordash.com/en-US/docs/reporting/overview/FAQ/), [Grubhub reporting overview](https://developer.grubhub.com/docs/6AWV4VW2XFayLI9SYrzugm/reporting-api-overview).

## Handling rules for analytics

- Preserve source platform, location, report version/columns, retrieval time, and raw IDs.
- Treat identifiers as strings; do not assume numeric-looking IDs are safe JavaScript numbers.
- Confirm timestamp timezone semantics before deriving local hour/day. Separate placement time from scheduled fulfillment time when forecasting kitchen workload.
- Preserve raw monetary values and verify their units before normalization; CSV values need explicit parsing.
- Count distinct orders for order volume and sum item quantities for dish volume. Do not sum repeated cart subtotals across item rows.
- Reconcile cancellations and adjustments; define whether the target is placed, fulfilled, or net sales demand.
- Deduplicate overlapping report pulls and live events. Platform records cover their own channels; combining them with POS exports can double-count the same sale.
- Label synthetic samples. They support development but cannot establish real-world forecast accuracy.

## Live integration references

Reporting is enough for initial historical analytics. Add live order events later for within-service demand changes.

- [DoorDash incoming orders and JSON webhook envelope](https://developer.doordash.com/en-US/docs/marketplace/how_to/order_integration/)
- [Grubhub order workflow and JSON sample](https://developer.grubhub.com/docs/3FrsnGXiR1Yt3Olm4sDWuM/order-workflow)

Order fulfillment integrations have confirmation/status obligations. Confirm a supported analytics integration arrangement before making this agent an order recipient.
