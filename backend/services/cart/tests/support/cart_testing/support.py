from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI
from redis.asyncio import Redis

from cart.application.errors import CatalogUnavailableError
from cart.domain.product import ProductState
from cart.infra.memory import InMemoryCartStore, InMemoryProductProjection
from cart.main import create_cart_app
from cart.settings import CartSettings, RedisSettings
from ecommerce_auth import JwtSettings, Role
from ecommerce_auth.testing import StubTokenIssuer, build_stub_verifier

MEDIA_BASE_URL = "/media"
IMAGE_KEY = "products/RS-001/0b9c5d7e-1a02-4f7e-8a21-3f2b8c1e6d4a"


class SteppingClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        self.now += timedelta(seconds=1)
        return self.now


def product(
    sku: str = "RS-001",
    price: str = "89.99",
    stock: int = 10,
    version: int = 1,
    name: str = "Running Shoes",
    deleted: bool = False,
    image_key: str | None = IMAGE_KEY,
) -> ProductState:
    return ProductState(sku, name, Decimal(price), stock, version, deleted, image_key)


class FakeCatalog:
    def __init__(self, *products: ProductState) -> None:
        self.products = {item.sku: item for item in products}
        self.unavailable = False
        self.requests: list[str] = []

    def add(self, item: ProductState) -> None:
        self.products[item.sku] = item

    async def get(self, sku: str) -> ProductState | None:
        self.requests.append(sku)
        if self.unavailable:
            raise CatalogUnavailableError("catalog is down")
        return self.products.get(sku)


def cart_settings(**overrides: Any) -> CartSettings:
    values: dict[str, Any] = {
        "redis": RedisSettings(host="127.0.0.1", password="unused", port=1),
        "jwt": JwtSettings(jwks_url="http://auth.test/jwks.json", issuer="ecommerce-auth"),
        "media_public_base_url": MEDIA_BASE_URL,
    }
    return CartSettings(**(values | overrides))


class Stores:
    def __init__(self) -> None:
        self.carts = InMemoryCartStore()
        self.projection = InMemoryProductProjection()


def build_test_app(
    issuer: StubTokenIssuer,
    stores: Stores,
    catalog: FakeCatalog,
    clock: SteppingClock | None = None,
    redis: Redis | None = None,
) -> FastAPI:
    app = create_cart_app(
        cart_settings(),
        redis=redis,
        store=stores.carts,
        projection=stores.projection,
        catalog=catalog,
        clock=clock or SteppingClock(),
    )
    app.state.token_verifier = build_stub_verifier(issuer)
    return app


@asynccontextmanager
async def http_client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def bearer(
    issuer: StubTokenIssuer, user_id: UUID | None = None, role: Role = Role.CUSTOMER
) -> dict[str, str]:
    token = issuer.issue(subject=str(user_id or uuid4()), role=role)
    return {"Authorization": f"Bearer {token}"}
