"""Public request and response contracts; independent of ORM storage models."""

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Generic, Literal, TypeVar
from uuid import UUID

from pydantic import BaseModel, Field, field_serializer, model_validator

Source = Literal["doordash", "grubhub"]
ImportStatus = Literal["running", "succeeded", "failed"]
Fulfillment = Literal["pickup", "delivery"]
T = TypeVar("T")


class PageParams(BaseModel):
    limit: int = Field(default=100, ge=1, le=500)
    cursor: str | None = Field(default=None, max_length=4096)

    def filters(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"limit", "cursor"})


class StoreParams(PageParams):
    source: Source | None = None


class ItemParams(StoreParams):
    store_id: UUID | None = None


class SaleParams(ItemParams):
    date_start: date | None = None
    date_end: date | None = None

    @model_validator(mode="after")
    def validate_range(self) -> "SaleParams":
        if self.date_start and self.date_end and self.date_start >= self.date_end:
            raise ValueError("date_end must be after date_start")
        return self


class _OrderScope(BaseModel):
    """Store, period, and time-of-day filters shared by order search and dish ranking."""

    source: Source | None = None
    store_id: UUID | None = None
    store_name: str | None = Field(default=None, min_length=1, max_length=200)
    on_date: date | None = Field(default=None, alias="date")
    date_start: date | None = None
    date_end: date | None = None
    time_start: time | None = None
    time_end: time | None = None

    @model_validator(mode="after")
    def validate_period(self):
        if self.on_date and (self.date_start or self.date_end):
            raise ValueError("Use date, or date_start/date_end, not both")
        if self.on_date:
            self.date_start, self.date_end = self.on_date, self.on_date + timedelta(days=1)
        if self.date_start and self.date_end and self.date_start >= self.date_end:
            raise ValueError("date_end must be after date_start")
        if self.time_start and self.time_end and self.time_start == self.time_end:
            raise ValueError("time_start and time_end must differ")
        return self


class OrderFilterParams(_OrderScope, PageParams):
    item_name: str | None = Field(default=None, min_length=1, max_length=200)

    def filters(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"limit", "cursor", "on_date"})


class TopDishParams(_OrderScope):
    limit: int = Field(default=10, ge=1, le=100)


class ImportParams(StoreParams):
    status: ImportStatus | None = None


class Page(BaseModel, Generic[T]):
    data: list[T]
    next_cursor: str | None


class StoreOut(BaseModel):
    id: UUID
    source: Source
    external_store_id: str
    store_name: str
    timezone: str | None
    source_details: dict[str, Any]


class OrderOut(BaseModel):
    id: UUID
    source: Source
    store_id: UUID
    external_store_id: str
    external_order_id: str
    order_number: str | None
    placed_at_local: datetime
    timezone: str
    fulfillment: Fulfillment | None
    subtotal: Decimal | None
    source_details: dict[str, Any]
    last_import_run_id: UUID
    is_synthetic: bool


class OrderLineOut(BaseModel):
    id: UUID
    source: Source
    store_id: UUID
    external_store_id: str
    order_id: UUID
    external_order_id: str
    order_number: str | None
    placed_at_local: datetime
    timezone: str
    fulfillment: Fulfillment | None
    external_line_id: str | None
    external_item_id: str
    item_name: str
    category_name: str | None
    quantity: Decimal
    unit_price: Decimal | None
    modifiers: list[dict[str, Any]] | None
    source_details: dict[str, Any]
    last_import_run_id: UUID
    is_synthetic: bool

    @field_serializer("quantity", when_used="json")
    def serialize_quantity(self, value: Decimal) -> int | str:
        return int(value) if value == value.to_integral_value() else str(value)


class ItemOut(BaseModel):
    source: Source
    store_id: UUID
    external_store_id: str
    external_item_id: str
    item_name: str
    category_name: str | None
    last_seen_at_local: datetime
    last_import_run_id: UUID
    is_synthetic: bool


class ImportOut(BaseModel):
    id: UUID
    source: Source
    report_type: str
    report_version: int | None
    requested_columns: list[str]
    date_start: date | None
    date_end: date | None
    provider_report_id: str | None
    status: ImportStatus
    started_at: datetime
    completed_at: datetime | None
    row_count: int
    is_synthetic: bool
    error: str | None


class OrderItemOut(BaseModel):
    item_name: str
    category_name: str | None
    quantity: Decimal
    unit_price: Decimal | None

    @field_serializer("quantity", when_used="json")
    def serialize_quantity(self, value: Decimal) -> int | str:
        return int(value) if value == value.to_integral_value() else str(value)


class FilteredOrderOut(BaseModel):
    id: UUID
    source: Source
    store_id: UUID
    store_name: str
    external_order_id: str
    order_number: str | None
    placed_at_local: datetime
    timezone: str
    fulfillment: Fulfillment | None
    items: list[OrderItemOut]
    is_synthetic: bool


class DishRankOut(BaseModel):
    rank: int
    item_name: str
    category_name: str | None
    units: Decimal
    orders: int

    @field_serializer("units", when_used="json")
    def serialize_units(self, value: Decimal) -> int | str:
        return int(value) if value == value.to_integral_value() else str(value)


class TopDishesOut(BaseModel):
    date_start: date | None
    date_end: date | None
    data: list[DishRankOut]
