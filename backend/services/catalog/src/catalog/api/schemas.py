from datetime import datetime
from decimal import Decimal
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StrictInt

from catalog.domain.product import Category, Product


class CategoryOut(BaseModel):
    id: UUID
    name: str
    slug: str

    @classmethod
    def from_domain(cls, category: Category) -> Self:
        return cls(id=category.id, name=category.name, slug=category.slug)


class CategoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str


class ProductWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str | None = None
    category_id: UUID | None = None
    price: Decimal
    stock: StrictInt
    weight_kg: Decimal | None = None


class ProductCreate(ProductWrite):
    sku: str


class ProductOut(BaseModel):
    sku: str
    name: str
    description: str | None
    category: CategoryOut | None
    price: Decimal
    stock: int
    weight_kg: Decimal | None
    version: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, product: Product) -> Self:
        return cls(
            sku=product.sku,
            name=product.name,
            description=product.description,
            category=CategoryOut.from_domain(product.category) if product.category else None,
            price=product.price,
            stock=product.stock,
            weight_kg=product.weight_kg,
            version=product.version,
            created_at=product.created_at,
            updated_at=product.updated_at,
        )


class ProductPage(BaseModel):
    items: list[ProductOut]
    next_cursor: str | None = None


class FieldProblem(BaseModel):
    location: str
    message: str
    type: str


class ProblemOut(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str
    request_id: str | None = None
    errors: list[FieldProblem] | None = None
