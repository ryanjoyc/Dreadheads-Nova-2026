"""Order search and dish ranking built on the existing read endpoints' query functions.

Everything here reads through `queries.list_stores` and `queries.list_order_lines`, the
same functions behind `GET /stores` and `GET /order-lines`, as the README recommends for
analytics. Following the README: order volume counts distinct order IDs, dish volume sums
line quantities, and dishes are grouped by item name across platforms.
"""

from collections import defaultdict
from collections.abc import Iterator
from datetime import datetime, time
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from nova_backend import queries
from nova_backend.pagination import InvalidCursor, decode_cursor, encode_cursor
from nova_backend.schemas import (
    OrderFilterParams,
    OrderScope,
    SaleParams,
    StoreParams,
    TopDishParams,
)

PAGE = 500  # The read endpoints' maximum page size.


def _pages(fetch: Any, params: Any) -> Iterator[dict[str, Any]]:
    """Follow next_cursor through every page of a read endpoint's query function."""
    while True:
        page = fetch(params)
        yield from page["data"]
        if page["next_cursor"] is None:
            return
        params = params.model_copy(update={"cursor": page["next_cursor"]})


def _store_names(session: Session, params: OrderScope) -> dict[UUID, str]:
    stores = _pages(
        lambda p: queries.list_stores(session, p),
        StoreParams(source=params.source, limit=PAGE),
    )
    return {store["id"]: store["store_name"] for store in stores}


def _in_time_window(placed: datetime, start: time | None, end: time | None) -> bool:
    clock = placed.time()
    if start and end and start > end:  # Crosses midnight, e.g. 22:00 to 02:00.
        return clock >= start or clock < end
    return (start is None or clock >= start) and (end is None or clock < end)


def scoped_lines(session: Session, params: OrderScope) -> Iterator[tuple[dict[str, Any], str]]:
    """Order lines from /order-lines filters, narrowed by store name and time of day.

    Params with exact `start`/`end` moments (TopDishParams) are narrowed to those too.
    """
    names = _store_names(session, params)
    wanted = params.store_name.casefold() if params.store_name else None
    allowed = {sid for sid, name in names.items() if wanted is None or wanted in name.casefold()}
    sale_params = SaleParams(
        source=params.source,
        store_id=params.store_id,
        date_start=params.date_start,
        date_end=params.date_end,
        limit=PAGE,
    )
    for line in _pages(lambda p: queries.list_order_lines(session, p), sale_params):
        if line["store_id"] not in allowed:
            continue
        placed = line["placed_at_local"]
        if not _in_time_window(placed, params.time_start, params.time_end):
            continue
        start, end = getattr(params, "start", None), getattr(params, "end", None)
        if (start and placed < start) or (end and placed >= end):
            continue
        yield line, names[line["store_id"]]


def filter_orders(session: Session, params: OrderFilterParams) -> dict[str, Any]:
    """Orders matching store, period, time of day, and dish name, oldest first."""
    orders: dict[UUID, dict[str, Any]] = {}
    for line, store_name in scoped_lines(session, params):
        order = orders.get(line["order_id"])
        if order is None:
            order = orders[line["order_id"]] = {
                "id": line["order_id"],
                "source": line["source"],
                "store_id": line["store_id"],
                "store_name": store_name,
                "external_order_id": line["external_order_id"],
                "order_number": line["order_number"],
                "placed_at_local": line["placed_at_local"],
                "timezone": line["timezone"],
                "fulfillment": line["fulfillment"],
                "is_synthetic": line["is_synthetic"],
                "items": [],
            }
        order["items"].append(
            {
                "item_name": line["item_name"],
                "category_name": line["category_name"],
                "quantity": line["quantity"],
                "unit_price": line["unit_price"],
            }
        )

    matches = list(orders.values())
    if params.item_name:
        wanted = params.item_name.casefold()
        matches = [
            o for o in matches if any(wanted in i["item_name"].casefold() for i in o["items"])
        ]
    matches.sort(key=lambda o: (o["placed_at_local"], o["id"]))

    filters = params.filters()
    after = decode_cursor(params.cursor, "orders-filter", filters, key_count=2)
    if after is not None:
        try:
            after_key = (datetime.fromisoformat(after[0]), UUID(after[1]))
        except ValueError as exc:
            raise InvalidCursor("Invalid cursor key") from exc
        matches = [o for o in matches if (o["placed_at_local"], o["id"]) > after_key]

    data = matches[: params.limit]
    cursor = None
    if len(matches) > params.limit:
        last = data[-1]
        cursor = encode_cursor(
            "orders-filter", filters, [last["placed_at_local"].isoformat(), str(last["id"])]
        )
    return {"data": data, "next_cursor": cursor}


def top_dishes(session: Session, params: TopDishParams) -> dict[str, Any]:
    """Rank dishes by units sold, then by number of orders, then by name."""
    units: dict[str, Decimal] = defaultdict(Decimal)
    orders: dict[str, set[UUID]] = defaultdict(set)
    categories: dict[str, str | None] = {}
    for line, _store_name in scoped_lines(session, params):
        name = line["item_name"]
        units[name] += line["quantity"]
        orders[name].add(line["order_id"])
        categories[name] = categories.get(name) or line["category_name"]

    ranked = sorted(units, key=lambda n: (-units[n], -len(orders[n]), n))[: params.limit]
    return {
        "date_start": params.date_start,
        "date_end": params.date_end,
        "start": params.start,
        "end": params.end,
        "data": [
            {
                "rank": rank,
                "item_name": name,
                "category_name": categories[name],
                "units": units[name],
                "orders": len(orders[name]),
            }
            for rank, name in enumerate(ranked, start=1)
        ],
    }
