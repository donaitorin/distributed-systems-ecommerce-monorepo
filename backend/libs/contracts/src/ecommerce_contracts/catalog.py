from decimal import Decimal
from typing import Final

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

CATALOG_TOPIC: Final = "catalog.events"
PRODUCT_UPDATED: Final = "product.updated"
PRODUCT_DELETED: Final = "product.deleted"


class ProductUpdatedV1(BaseModel):
    model_config = ConfigDict(frozen=True)

    sku: str = Field(min_length=1)
    name: str = Field(min_length=1)
    price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    stock: int = Field(ge=0)
    image_key: str | None = None
    version: int = Field(ge=1)
    occurred_at: AwareDatetime


class ProductDeletedV1(BaseModel):
    model_config = ConfigDict(frozen=True)

    sku: str = Field(min_length=1)
    version: int = Field(ge=1)
    occurred_at: AwareDatetime
