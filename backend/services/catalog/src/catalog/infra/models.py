from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from ecommerce_messaging import outbox_table, processed_events_table

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


SEARCH_VECTOR_EXPRESSION = (
    "setweight(to_tsvector('english'::regconfig, coalesce(name, '')), 'A') || "
    "setweight(to_tsvector('simple'::regconfig, sku), 'A') || "
    "setweight(to_tsvector('english'::regconfig, coalesce(description, '')), 'C')"
)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class CategoryModel(Base):
    __tablename__ = "categories"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    name: Mapped[str] = mapped_column(String(100))
    slug: Mapped[str] = mapped_column(String(120), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("uq_categories_name_lower", func.lower(name), unique=True),)


class ProductModel(Base):
    __tablename__ = "products"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    sku: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    category_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), index=True
    )
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    stock: Mapped[int] = mapped_column(Integer)
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    image_key: Mapped[str | None] = mapped_column(String(512))
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    search_vector: Mapped[str] = mapped_column(
        TSVECTOR, Computed(SEARCH_VECTOR_EXPRESSION, persisted=True), deferred=True
    )

    __table_args__ = (
        Index(
            "ix_products_search_vector",
            "search_vector",
            postgresql_using="gin",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_products_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_products_created_at_id",
            "created_at",
            "id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_products_price_id", "price", "id", postgresql_where=text("deleted_at IS NULL")),
        CheckConstraint("price >= 0", name="price_non_negative"),
        CheckConstraint("stock >= 0", name="stock_non_negative"),
        CheckConstraint("weight_kg IS NULL OR weight_kg >= 0", name="weight_non_negative"),
        CheckConstraint("version >= 1", name="version_positive"),
    )


IMPORT_STATUSES = (
    "uploaded",
    "validating",
    "rejected",
    "validated",
    "queued",
    "processing",
    "completed",
    "failed",
)


class ImportModel(Base):
    __tablename__ = "imports"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    filename: Mapped[str] = mapped_column(String(255))
    object_key: Mapped[str] = mapped_column(String(512))
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(20))
    created_by: Mapped[str] = mapped_column(String(100))
    failure_reason: Mapped[str | None] = mapped_column(Text)
    report: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    category_snapshot: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    processed_rows: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    created_rows: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    updated_rows: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    restored_rows: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    unchanged_rows: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "status IN (" + ", ".join(f"'{item}'" for item in IMPORT_STATUSES) + ")",
            name="status_known",
        ),
        Index(
            "uq_imports_sha256_unless_failed",
            "sha256",
            unique=True,
            postgresql_where=text("status <> 'failed'"),
        ),
        Index("ix_imports_created_at", "created_at"),
    )


class ImportProblemModel(Base):
    __tablename__ = "import_problems"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    import_id: Mapped[UUID] = mapped_column(ForeignKey("imports.id", ondelete="CASCADE"))
    severity: Mapped[str] = mapped_column(String(7))
    row: Mapped[int | None] = mapped_column(Integer)
    column_name: Mapped[str | None] = mapped_column(String(100))
    value: Mapped[str | None] = mapped_column(Text)
    code: Mapped[str] = mapped_column(String(50))
    reason: Mapped[str] = mapped_column(Text)

    __table_args__ = (Index("ix_import_problems_import_id_id", "import_id", "id"),)


OUTBOX = outbox_table(Base.metadata)
PROCESSED_EVENTS = processed_events_table(Base.metadata)
