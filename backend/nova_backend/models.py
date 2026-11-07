"""Storage shapes. API and provider formats are separate boundary models."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class SourceStore(Base):
    __tablename__ = "source_stores"
    __table_args__ = (
        UniqueConstraint("source", "external_store_id", name="uq_source_store"),
        CheckConstraint("source IN ('doordash', 'grubhub')", name="ck_store_source"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    external_store_id: Mapped[str] = mapped_column(Text, nullable=False)
    store_name: Mapped[str] = mapped_column(Text, nullable=False)
    timezone: Mapped[str | None] = mapped_column(Text)
    source_details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class ImportRun(Base):
    __tablename__ = "import_runs"
    __table_args__ = (
        CheckConstraint("source IN ('doordash', 'grubhub')", name="ck_import_source"),
        CheckConstraint("status IN ('running', 'succeeded', 'failed')", name="ck_import_status"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    report_type: Mapped[str] = mapped_column(Text, nullable=False)
    report_version: Mapped[int | None] = mapped_column(Integer)
    requested_columns: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    date_start: Mapped[date | None] = mapped_column(Date)
    date_end: Mapped[date | None] = mapped_column(Date)
    provider_report_id: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw_file_reference: Mapped[str | None] = mapped_column(Text)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    row_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("source_store_id", "external_order_id", name="uq_store_order"),
        CheckConstraint(
            "fulfillment IS NULL OR fulfillment IN ('pickup', 'delivery')",
            name="ck_order_fulfillment",
        ),
        CheckConstraint("subtotal IS NULL OR subtotal >= 0", name="ck_order_subtotal"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    source_store_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source_stores.id"), nullable=False, index=True
    )
    external_order_id: Mapped[str] = mapped_column(Text, nullable=False)
    order_number: Mapped[str | None] = mapped_column(Text)
    placed_at_local: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    source_timezone: Mapped[str] = mapped_column(Text, nullable=False)
    fulfillment: Mapped[str | None] = mapped_column(Text)
    subtotal: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    source_details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    last_import_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("import_runs.id"), nullable=False, index=True
    )


class OrderLine(Base):
    __tablename__ = "order_lines"
    __table_args__ = (
        UniqueConstraint("order_id", "external_line_id", name="uq_order_external_line"),
        CheckConstraint("quantity > 0", name="ck_line_quantity"),
        CheckConstraint("unit_price IS NULL OR unit_price >= 0", name="ck_line_price"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    external_line_id: Mapped[str | None] = mapped_column(Text)
    external_item_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    item_name: Mapped[str] = mapped_column(Text, nullable=False)
    category_name: Mapped[str | None] = mapped_column(Text)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    modifiers: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    source_details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
