# NOVA sales backend

Local Python 3.12 / FastAPI / PostgreSQL 17 backend for synthetic DoorDash and Grubhub reports. Docker Compose is the only required host runtime. No provider credentials are needed.

This backend serves observed sales records. It does not calculate forecasts, ingredient needs, or inventory, and does not implement the recommendation endpoints or connect the prep wireframe.

## Start the backend

Run these commands from `backend/`:

```sh
cp .env.example .env
docker compose build
docker compose up -d db
docker compose run --rm migrate
docker compose up -d api
```

The API is available at [http://127.0.0.1:8000](http://127.0.0.1:8000). Interactive documentation is at [/docs](http://127.0.0.1:8000/docs); the machine-readable contract is at [/openapi.json](http://127.0.0.1:8000/openapi.json). The root URL has no application route.

Database migrations are explicit. Run `docker compose run --rm migrate` after pulling schema changes; starting the API does not create tables. Alembic records applied versions, so repeating the command does not recreate existing tables. Create future migrations using `docker compose run --rm -v "$PWD:/app" migrate alembic revision --autogenerate -m 'describe change'`, then review the generated migration before applying it. The writable backend mount saves the new migration into your checkout.

Set `API_PORT`, `DB_PORT`, or `CORS_ORIGINS` in `.env` before starting if the default ports/origins are unsuitable. Host ports bind only to loopback. The local database is `nova_sales`, user `nova`, password `nova_local`, exposed at `127.0.0.1:55433`. These are development values, not production credentials. The API connects over the Compose network rather than the host port. CORS origins are a JSON array of explicit HTTP localhost origins.

After changing code, rebuild with `docker compose build` and recreate the API with `docker compose up -d api`. Dependencies are pinned in `requirements.lock`; the Docker build installs the lock before the application.

## Import the small fixtures

Both files contain six complete orders, three per platform store. They are derived from the committed synthetic reports without regenerating the dataset.

```sh
docker compose run --rm api python -m nova_backend.imports --source doordash --file /app/fixtures/doordash_order_detail.csv --synthetic --complete-orders
docker compose run --rm api python -m nova_backend.imports --source grubhub --file /app/fixtures/grubhub_menu_line_items.csv --synthetic --complete-orders
```

Expected combined records: four platform stores, twelve orders, and twenty-one item lines. Repeat either command to refresh the included orders without duplicating sales. Each attempt creates its own import audit record.

`--synthetic` and `--complete-orders` are required assertions. Only use files known to contain complete line sets for their included orders. The importer cannot prove completeness from a CSV. It refreshes those orders and leaves absent orders unchanged. Order IDs stay stable; internal item-line IDs can change after a refresh.

For other local files, place them inside this repository and reference them through the read-only `/workspace/` mount. Original files are archived under a unique import ID in the `raw-imports` volume. Parsed line `source_details` preserve original CSV cells, row numbers, and time warnings. Files and extra fields can contain merchant information; keep this local until access controls are added.

Optional CLI metadata: `--report-version` for DoorDash (default 2, minimum 2) and `--provider-report-id`. Grubhub has no configured report version. IDs remain strings, including leading zeros. Prices and quantities use exact decimal storage. Real exports still need validation of units, modifier encoding, timestamp meanings, and complete-order semantics.

`import_runs.requested_columns` records the local file's columns. `date_start` and exclusive `date_end` describe observed placement dates, not requested provider coverage or proof that every intervening date is complete. `completed_at` is import completion time, not a provider data cutoff.

## Query the data

```sh
curl 'http://127.0.0.1:8000/stores'
curl 'http://127.0.0.1:8000/orders?source=doordash&limit=2'
curl 'http://127.0.0.1:8000/order-lines?date_start=2026-05-01&date_end=2026-05-02'
curl 'http://127.0.0.1:8000/items?source=grubhub'
curl 'http://127.0.0.1:8000/imports?status=succeeded'
```

| Endpoint | Filters | Meaning |
| --- | --- | --- |
| `/stores` | `source` | Platform store identities |
| `/orders` | `source`, `store_id`, `date_start`, `date_end` | One row per order |
| `/order-lines` | Same as orders | Joined source/store/order/item records for analytics |
| `/items` | `source`, `store_id` | Observed store-scoped items and latest labels, not a complete menu |
| `/imports` | `source`, `status` | Import status and provenance without raw filesystem paths |

All five endpoints accept `limit` (default 100, maximum 500) and `cursor`. Responses contain `data` and `next_cursor`. Pass the cursor unchanged with the same endpoint and filters to get the next page. Cursors are pagination positions, not authorization tokens. Pagination assumes the dataset is unchanged between requests.

`store_id` is the internal UUID from `/stores`, not a provider's external store ID. Dates filter store-local placement dates with an inclusive start and exclusive end. Unknown valid store UUIDs return empty lists. Invalid filters/cursors return HTTP 400; unexpected server failures return a generic HTTP 500.

Prices are decimal strings or null. Whole-number quantities are JSON integers; fractional quantities are decimal strings to preserve precision. Local timestamps have no UTC offset and are paired with their source timezone. Ambiguous local times are preserved with a warning; nonexistent local times fail validation. No absolute timestamp is guessed.

Every order/line carries its source and import provenance, including synthetic status. Count distinct internal order IDs for order volume; sum line quantities for dish volume. Never sum repeated raw subtotals across lines. Grubhub subtotals and unconfirmed DoorDash modifiers stay null.

There is no automatic cross-platform restaurant or dish mapping. The feeds share a schema while retaining separate source identities. Analytics may reuse query functions under `nova_backend.queries` inside trusted Python code, or consume these endpoints.

## Verify the implementation

```sh
docker compose --profile test run --rm test
docker compose run --rm api ruff check .
docker compose run --rm api ruff format --check .
docker compose run --rm api python scripts/http_smoke.py http://api:8000
```

The HTTP smoke check requires a running API and both seeded fixtures. Run database verification commands serially: pytest and the full-dataset check share and clear the disposable test database. The test suite applies migrations to `db-test/nova_sales_test`, truncates its sales data between tests, and exercises migration downgrade/re-upgrade only there. The test database uses temporary storage and a different password/network address from development. Test guards refuse other database hosts/names.

To reconcile the full platform files independently of the parser:

```sh
docker compose --profile test run --rm test alembic upgrade head
docker compose --profile test run --rm test python scripts/full_dataset_smoke.py
```

This clears only the disposable test database and imports both reports twice. Expected totals are recomputed with the standard CSV reader, then compared with PostgreSQL. The committed dataset currently has 45,056 orders, 85,833 item lines, and 100,096 units. Reference, recipe, and operations files are not imported. A later pytest run clears test records again.

## Operate locally

`docker compose logs api` shows application logs. A database error commonly means migrations have not run; check `docker compose run --rm migrate alembic current`. If an import fails, inspect `/imports?status=failed` or its CLI message. Failed imports do not partially update sales. Detailed raw files stay in local storage; public errors omit raw rows, SQL, and private paths.

`docker compose restart api db` preserves development data. `docker compose down` stops this project's containers while retaining named volumes. Do not use `down -v` unless you explicitly intend to erase this backend's development database and archived files. Leave other Docker projects untouched.

This is a local synthetic-data implementation. There is no authentication or scheduled sync. Do not expose it publicly or load real merchant data before authorization and actual-export validation are designed.
