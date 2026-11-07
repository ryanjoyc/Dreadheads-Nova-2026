"""Database-backed retrieval functions shared by HTTP and trusted analytics code."""

from datetime import datetime, time
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, tuple_
from sqlalchemy.orm import Session

from nova_backend.models import ImportRun, Order, OrderLine, SourceStore
from nova_backend.pagination import InvalidCursor, decode_cursor, encode_cursor
from nova_backend.schemas import ImportParams, ItemParams, SaleParams, StoreParams


def _uuid_after(cursor: str | None, scope: str, filters: dict[str, Any]) -> UUID | None:
    keys = decode_cursor(cursor, scope, filters)
    if keys is None:
        return None
    try:
        return UUID(keys[0])
    except ValueError as exc:
        raise InvalidCursor("Invalid cursor key") from exc


def _page(
    session: Session,
    statement: Any,
    key: Any,
    scope: str,
    params: Any,
) -> dict[str, Any]:
    filters = params.filters()
    after = _uuid_after(params.cursor, scope, filters)
    if after is not None:
        statement = statement.where(key > after)
    rows = session.execute(statement.order_by(key).limit(params.limit + 1)).mappings().all()
    more = len(rows) > params.limit
    data = [dict(row) for row in rows[: params.limit]]
    cursor = encode_cursor(scope, filters, [str(data[-1]["id"])]) if more else None
    return {"data": data, "next_cursor": cursor}


def list_stores(session: Session, params: StoreParams) -> dict[str, Any]:
    stmt = select(
        SourceStore.id,
        SourceStore.source,
        SourceStore.external_store_id,
        SourceStore.store_name,
        SourceStore.timezone,
        SourceStore.source_details,
    )
    if params.source:
        stmt = stmt.where(SourceStore.source == params.source)
    return _page(session, stmt, SourceStore.id, "stores", params)


def _sales_filters(statement: Any, params: SaleParams | ItemParams) -> Any:
    if params.source:
        statement = statement.where(SourceStore.source == params.source)
    if params.store_id:
        statement = statement.where(Order.source_store_id == params.store_id)
    if isinstance(params, SaleParams):
        if params.date_start:
            statement = statement.where(
                Order.placed_at_local >= datetime.combine(params.date_start, time.min)
            )
        if params.date_end:
            statement = statement.where(
                Order.placed_at_local < datetime.combine(params.date_end, time.min)
            )
    return statement


def list_orders(session: Session, params: SaleParams) -> dict[str, Any]:
    stmt = (
        select(
            Order.id,
            SourceStore.source,
            Order.source_store_id.label("store_id"),
            SourceStore.external_store_id,
            Order.external_order_id,
            Order.order_number,
            Order.placed_at_local,
            Order.source_timezone.label("timezone"),
            Order.fulfillment,
            Order.subtotal,
            Order.source_details,
            Order.last_import_run_id,
            ImportRun.is_synthetic,
        )
        .join(SourceStore, Order.source_store_id == SourceStore.id)
        .join(ImportRun, Order.last_import_run_id == ImportRun.id)
    )
    return _page(session, _sales_filters(stmt, params), Order.id, "orders", params)


def list_order_lines(session: Session, params: SaleParams) -> dict[str, Any]:
    stmt = (
        select(
            OrderLine.id,
            SourceStore.source,
            Order.source_store_id.label("store_id"),
            SourceStore.external_store_id,
            Order.id.label("order_id"),
            Order.external_order_id,
            Order.order_number,
            Order.placed_at_local,
            Order.source_timezone.label("timezone"),
            Order.fulfillment,
            OrderLine.external_line_id,
            OrderLine.external_item_id,
            OrderLine.item_name,
            OrderLine.category_name,
            OrderLine.quantity,
            OrderLine.unit_price,
            OrderLine.modifiers,
            OrderLine.source_details,
            Order.last_import_run_id,
            ImportRun.is_synthetic,
        )
        .select_from(OrderLine)
        .join(Order, OrderLine.order_id == Order.id)
        .join(SourceStore, Order.source_store_id == SourceStore.id)
        .join(ImportRun, Order.last_import_run_id == ImportRun.id)
    )
    return _page(session, _sales_filters(stmt, params), OrderLine.id, "order-lines", params)


def list_items(session: Session, params: ItemParams) -> dict[str, Any]:
    observed = (
        select(
            SourceStore.source,
            Order.source_store_id.label("store_id"),
            SourceStore.external_store_id,
            OrderLine.external_item_id,
            OrderLine.item_name,
            OrderLine.category_name,
            Order.placed_at_local.label("last_seen_at_local"),
            Order.last_import_run_id,
            ImportRun.is_synthetic,
            func.row_number()
            .over(
                partition_by=(Order.source_store_id, OrderLine.external_item_id),
                order_by=(Order.placed_at_local.desc(), Order.id.desc(), OrderLine.id.desc()),
            )
            .label("rank"),
        )
        .select_from(OrderLine)
        .join(Order, OrderLine.order_id == Order.id)
        .join(SourceStore, Order.source_store_id == SourceStore.id)
        .join(ImportRun, Order.last_import_run_id == ImportRun.id)
    )
    latest = _sales_filters(observed, params).subquery()
    stmt = select(*(column for column in latest.c if column.key != "rank")).where(
        latest.c.rank == 1
    )
    filters = params.filters()
    after = decode_cursor(params.cursor, "items", filters, key_count=2)
    if after is not None:
        try:
            store_id = UUID(after[0])
        except ValueError as exc:
            raise InvalidCursor("Invalid cursor key") from exc
        stmt = stmt.where(
            tuple_(latest.c.store_id, latest.c.external_item_id) > tuple_(store_id, after[1])
        )
    rows = (
        session.execute(
            stmt.order_by(latest.c.store_id, latest.c.external_item_id).limit(params.limit + 1)
        )
        .mappings()
        .all()
    )
    data = [dict(row) for row in rows[: params.limit]]
    cursor = None
    if len(rows) > params.limit:
        cursor = encode_cursor(
            "items", filters, [str(data[-1]["store_id"]), data[-1]["external_item_id"]]
        )
    return {"data": data, "next_cursor": cursor}


def list_imports(session: Session, params: ImportParams) -> dict[str, Any]:
    # Internal file paths and unfiltered exception details are not public fields.
    stmt = select(
        ImportRun.id,
        ImportRun.source,
        ImportRun.report_type,
        ImportRun.report_version,
        ImportRun.requested_columns,
        ImportRun.date_start,
        ImportRun.date_end,
        ImportRun.provider_report_id,
        ImportRun.status,
        ImportRun.started_at,
        ImportRun.completed_at,
        ImportRun.row_count,
        ImportRun.is_synthetic,
        ImportRun.error,
    )
    if params.source:
        stmt = stmt.where(ImportRun.source == params.source)
    if params.status:
        stmt = stmt.where(ImportRun.status == params.status)
    return _page(session, stmt, ImportRun.id, "imports", params)
