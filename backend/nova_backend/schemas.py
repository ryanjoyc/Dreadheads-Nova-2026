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


class OrderScope(BaseModel):
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


class OrderFilterParams(OrderScope, PageParams):
    item_name: str | None = Field(default=None, min_length=1, max_length=200)

    def filters(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"limit", "cursor", "on_date"})


class TopDishParams(OrderScope):
    limit: int = Field(default=10, ge=1, le=100)
    start: datetime | None = Field(
        default=None, description="Exact store-local start, e.g. 2026-05-01T11:00 (inclusive)"
    )
    end: datetime | None = Field(
        default=None, description="Exact store-local end, e.g. 2026-05-01T13:30 (exclusive)"
    )

    @model_validator(mode="after")
    def validate_moments(self) -> "TopDishParams":
        if self.start is None and self.end is None:
            return self
        if self.on_date or self.date_start or self.date_end:
            raise ValueError("Use start/end, or date/date_start/date_end, not both")
        if self.start and self.end and self.start >= self.end:
            raise ValueError("end must be after start")
        # Narrow the /order-lines read to the days involved; exact moments filter after.
        self.date_start = self.start.date() if self.start else None
        self.date_end = self.end.date() + timedelta(days=1) if self.end else None
        return self


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
    start: datetime | None
    end: datetime | None
    data: list[DishRankOut]


Confidence = Literal["high", "medium", "low"]


class RushParams(BaseModel):
    on_date: date = Field(alias="date", description="Store-local day to predict")
    from_time: time = Field(
        default=time(0, 0),
        alias="time",
        description="Current store-local time; only rushes underway or still to come are returned",
    )
    until: time | None = Field(default=None, description="Ignore rushes starting at or after this")
    source: Source | None = None
    store_id: UUID | None = None
    store_name: str | None = Field(default=None, min_length=1, max_length=200)
    context: str | None = Field(
        default=None,
        max_length=500,
        description="What the manager knows about the day, e.g. 'home football game at 1pm'",
    )
    weeks: int = Field(default=8, ge=1, le=26, description="Same-weekday history to average")
    slot_minutes: int = Field(default=15, description="15, 30, or 60")
    use_agent: bool = True

    @model_validator(mode="after")
    def validate_window(self) -> "RushParams":
        if self.slot_minutes not in (15, 30, 60):
            raise ValueError("slot_minutes must be 15, 30, or 60")
        if self.until and self.until <= self.from_time:
            raise ValueError("until must be after time")
        return self

    def scope(self) -> OrderScope:
        return OrderScope(source=self.source, store_id=self.store_id, store_name=self.store_name)


class RushWindowOut(BaseModel):
    start: str
    end: str
    peak_at: str
    status: Literal["in_progress", "upcoming"]
    minutes_until: int
    expected_orders: float
    expected_peak_orders: float
    intensity: float = Field(description="Peak slot vs a typical active slot")
    consistency: float = Field(description="Share of history days that were busy in this window")
    confidence: Confidence
    multiplier: float = Field(description="Agent adjustment applied to the forecast, 0.5-2.0")
    clamped_from: float | None
    actual_orders: int | None = Field(description="Real orders in the window, if already recorded")
    reason: str


class RushSlotOut(BaseModel):
    start: str
    expected_orders: float
    actual_orders: int | None
    is_rush: bool


class AgentStepOut(BaseModel):
    tool: str
    args: dict[str, Any]
    result: str


class RushHoursOut(BaseModel):
    date: date
    weekday: str
    time: time
    until: time | None
    slot_minutes: int
    method: Literal["agent", "baseline"]
    model: str | None
    history_days: list[date]
    typical_orders_per_slot: float
    rush_threshold: float
    rush_hours: list[RushWindowOut]
    slots: list[RushSlotOut]
    summary: str
    flags: list[str]
    agent_trace: list[AgentStepOut]
