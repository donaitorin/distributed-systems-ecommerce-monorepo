from datetime import datetime
from decimal import Decimal
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from catalog.api.media import MediaUrls
from catalog.domain.listing import ProductListing
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
    image_url: str | None = Field(
        default=None, description="Public URL of the 1200 px WebP image, null without an image"
    )
    thumbnail_url: str | None = Field(
        default=None, description="Public URL of the 400 px WebP thumbnail, null without an image"
    )
    version: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, product: Product, media: MediaUrls) -> Self:
        return cls(
            sku=product.sku,
            name=product.name,
            description=product.description,
            category=CategoryOut.from_domain(product.category) if product.category else None,
            price=product.price,
            stock=product.stock,
            weight_kg=product.weight_kg,
            image_url=media.image(product.image_key),
            thumbnail_url=media.thumbnail(product.image_key),
            version=product.version,
            created_at=product.created_at,
            updated_at=product.updated_at,
        )


class ProductPage(BaseModel):
    items: list[ProductOut]
    next_cursor: str | None = Field(
        default=None, description="Opaque cursor for the next page, null on the last page"
    )
    prev_cursor: str | None = Field(
        default=None, description="Opaque cursor for the previous page, null on the first page"
    )
    total: int = Field(
        default=0,
        description="Number of matching products; an estimate unless total_exact is true",
    )
    total_exact: bool = Field(
        default=True,
        description="True when total is an exact count, false when it is a planner estimate",
    )

    @classmethod
    def from_domain(cls, listing: ProductListing, media: MediaUrls) -> Self:
        return cls(
            items=[ProductOut.from_domain(item, media) for item in listing.items],
            next_cursor=listing.next_cursor,
            prev_cursor=listing.prev_cursor,
            total=listing.total.value,
            total_exact=listing.total.exact,
        )


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
