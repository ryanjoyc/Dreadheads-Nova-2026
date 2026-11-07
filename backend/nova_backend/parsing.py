"""Parse the supported synthetic report formats into validated domain records."""

import csv
import json
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class ReportValidationError(ValueError):
    """Safe diagnostics which do not include raw row values or file paths."""


@dataclass
class ParsedLine:
    external_line_id: str | None
    external_item_id: str
    item_name: str
    category_name: str | None
    quantity: Decimal
    unit_price: Decimal | None
    modifiers: list[dict] | None
    source_details: dict


@dataclass
class ParsedOrder:
    external_store_id: str
    external_order_id: str
    order_number: str | None
    placed_at_local: datetime
    source_timezone: str
    fulfillment: str | None
    subtotal: Decimal | None
    source_details: dict
    lines: list[ParsedLine] = field(default_factory=list)

    def metadata(self) -> tuple:
        return (
            self.order_number,
            self.placed_at_local,
            self.source_timezone,
            self.fulfillment,
            self.subtotal,
            self.source_details,
        )


@dataclass
class ParsedStore:
    external_store_id: str
    store_name: str
    timezone: str
    source_details: dict


@dataclass
class ParsedReport:
    stores: dict[str, ParsedStore]
    orders: dict[tuple[str, str], ParsedOrder]
    columns: list[str]
    row_count: int
    date_start: date | None
    date_end: date | None


def required(row: dict, key: str) -> str:
    value = row.get(key)
    if value is None or not value.strip():
        raise ReportValidationError(f"missing {key}")
    return value.strip()


def optional(row: dict, key: str) -> str | None:
    value = row.get(key)
    return value.strip() if value and value.strip() else None


def number(value: str | int | float | Decimal | None, key: str, *, positive=False):
    if value is None or value == "":
        return None
    try:
        if isinstance(value, bool):
            raise InvalidOperation
        result = Decimal(str(value))
        if not result.is_finite() or result < 0 or (positive and result <= 0):
            raise InvalidOperation
        if result.as_tuple().exponent < -6 or result.adjusted() > 11:
            raise InvalidOperation
        return result
    except (ValueError, InvalidOperation):
        raise ReportValidationError(f"invalid {key}") from None


def boolean(value: str, key: str) -> bool:
    if value.lower() not in {"true", "false"}:
        raise ReportValidationError(f"invalid {key}")
    return value.lower() == "true"


def local_timestamp(day: str, clock: str, timezone: str) -> tuple[datetime, list[str]]:
    try:
        zone = ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise ReportValidationError("invalid timezone") from None
    try:
        parsed_time = time.fromisoformat(clock)
        if parsed_time.tzinfo is not None:
            raise ValueError
        timestamp = datetime.combine(date.fromisoformat(day), parsed_time)
    except ValueError:
        raise ReportValidationError("invalid local placement timestamp") from None
    offsets = set()
    for fold in (0, 1):
        candidate = timestamp.replace(tzinfo=zone, fold=fold)
        if candidate.astimezone(UTC).astimezone(zone).replace(tzinfo=None) == timestamp:
            offsets.add(candidate.utcoffset())
    if not offsets:
        raise ReportValidationError("nonexistent local placement timestamp")
    warnings = ["ambiguous_local_time_preserved_without_utc"] if len(offsets) > 1 else []
    return timestamp, warnings


def modifiers(value: str | None) -> list[dict] | None:
    if value is None or not value.strip():
        return None
    try:
        parsed = json.loads(value, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, TypeError):
        raise ReportValidationError("invalid menu_item_modifiers JSON") from None
    if not isinstance(parsed, list):
        raise ReportValidationError("menu_item_modifiers must be a JSON array")
    for modifier in parsed:
        if not isinstance(modifier, dict):
            raise ReportValidationError("invalid modifier object")
        if not all(k in modifier for k in ("name", "id", "price", "quantity")):
            raise ReportValidationError("modifier requires name, id, price, quantity")
        if any(
            not isinstance(modifier[key], str) or not modifier[key].strip()
            for key in ("name", "id")
        ):
            raise ReportValidationError("invalid modifier name or ID")
        if modifier["price"] is None or modifier["quantity"] is None:
            raise ReportValidationError("modifier price and quantity are required")
        if number(modifier["price"], "modifier price") is None:
            raise ReportValidationError("modifier price is required")
        if number(modifier["quantity"], "modifier quantity", positive=True) is None:
            raise ReportValidationError("modifier quantity is required")
    return parsed


def parse_row(source: str, row: dict, row_number: int):
    if source == "doordash":
        store_id = required(row, "store_id")
        order_id = required(row, "dd_order_number")
        tz = required(row, "timezone")
        timestamp, warnings = local_timestamp(
            required(row, "order_place_date"), required(row, "order_place_time"), tz
        )
        pickup = optional(row, "is_consumer_pickup")
        fulfillment = (
            ("pickup" if boolean(pickup, "is_consumer_pickup") else "delivery") if pickup else None
        )
        dashpass = optional(row, "dashpass")
        if dashpass:
            boolean(dashpass, "dashpass")
        order_number = order_id
        subtotal = number(optional(row, "subtotal"), "subtotal")
        order_keys = [
            "dd_order_number",
            "created_at",
            "mx_order_number",
            "external_order_id",
            "dashpass",
        ]
        store_keys = ["business_id", "business_name", "store_id", "store_name"]
        line = ParsedLine(
            external_line_id=required(row, "order_item_id"),
            external_item_id=required(row, "dd_item_id"),
            item_name=required(row, "item_name"),
            category_name=optional(row, "category_name"),
            quantity=number(
                required(row, "order_item_quantity"), "order_item_quantity", positive=True
            ),
            unit_price=number(optional(row, "unit_price"), "unit_price"),
            modifiers=None,
            source_details={"raw_row": row, "row_number": row_number, "warnings": warnings},
        )
    elif source == "grubhub":
        store_id = required(row, "grubhub_store_id")
        order_id = required(row, "order_uuid")
        tz = required(row, "order_time_zone")
        timestamp, warnings = local_timestamp(
            required(row, "order_date"), required(row, "order_time_local"), tz
        )
        fulfillment_raw = optional(row, "fullfillment_type")
        if fulfillment_raw and fulfillment_raw.upper() not in {"DELIVERY", "PICKUP"}:
            raise ReportValidationError("invalid fullfillment_type")
        fulfillment = fulfillment_raw.lower() if fulfillment_raw else None
        order_number = required(row, "order_number")
        subtotal = None
        order_keys = ["order_uuid", "order_number", "partner_order_id"]
        store_keys = ["grubhub_store_id", "store_name", "store_number", "external_id"]
        line = ParsedLine(
            external_line_id=None,
            external_item_id=required(row, "menu_item_id"),
            item_name=required(row, "menu_item_name"),
            category_name=optional(row, "menu_item_category_name"),
            quantity=number(
                required(row, "menu_item_quantity"), "menu_item_quantity", positive=True
            ),
            unit_price=number(optional(row, "menu_item_price"), "menu_item_price"),
            modifiers=modifiers(optional(row, "menu_item_modifiers")),
            source_details={"raw_row": row, "row_number": row_number, "warnings": warnings},
        )
    else:
        raise ReportValidationError("unsupported source")
    store = ParsedStore(
        store_id, required(row, "store_name"), tz, {k: optional(row, k) for k in store_keys}
    )
    order = ParsedOrder(
        store_id,
        order_id,
        order_number,
        timestamp,
        tz,
        fulfillment,
        subtotal,
        {k: optional(row, k) for k in order_keys},
    )
    return store, order, line


def parse_report(source: str, file: Path) -> ParsedReport:
    if source not in {"doordash", "grubhub"}:
        raise ReportValidationError("unsupported source")
    stores, orders, seen_lines = {}, {}, set()
    try:
        with file.open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream, strict=True)
            columns = reader.fieldnames
            if not columns or len(set(columns)) != len(columns):
                raise ReportValidationError("missing or duplicate CSV headers")
            required_columns = (
                {
                    "store_id",
                    "store_name",
                    "dd_order_number",
                    "order_place_date",
                    "order_place_time",
                    "timezone",
                    "order_item_id",
                    "dd_item_id",
                    "item_name",
                    "order_item_quantity",
                }
                if source == "doordash"
                else {
                    "grubhub_store_id",
                    "store_name",
                    "order_uuid",
                    "order_number",
                    "order_date",
                    "order_time_local",
                    "order_time_zone",
                    "menu_item_id",
                    "menu_item_name",
                    "menu_item_quantity",
                }
            )
            if not required_columns.issubset(columns):
                raise ReportValidationError("missing required CSV columns")
            row_count = 0
            for row_number, row in enumerate(reader, 2):
                try:
                    if None in row or None in row.values():
                        raise ReportValidationError(
                            "CSV row has a different field count than its header"
                        )
                    store, order, line = parse_row(source, row, row_number)
                    if (
                        store.external_store_id in stores
                        and stores[store.external_store_id] != store
                    ):
                        raise ReportValidationError("conflicting store metadata")
                    stores[store.external_store_id] = store
                    key = (store.external_store_id, order.external_order_id)
                    if key in orders:
                        if orders[key].metadata() != order.metadata():
                            raise ReportValidationError("conflicting order metadata")
                    else:
                        orders[key] = order
                    if line.external_line_id is not None:
                        line_key = (*key, line.external_line_id)
                        if line_key in seen_lines:
                            raise ReportValidationError("duplicate order_item_id within order")
                        seen_lines.add(line_key)
                    orders[key].lines.append(line)
                    row_count += 1
                except ReportValidationError as exc:
                    raise ReportValidationError(f"row {row_number}: {exc}") from None
    except (UnicodeError, csv.Error):
        raise ReportValidationError("invalid CSV encoding or structure") from None
    dates = [order.placed_at_local.date() for order in orders.values()]
    return ParsedReport(
        stores,
        orders,
        columns,
        row_count,
        min(dates) if dates else None,
        max(dates) if dates else None,
    )
