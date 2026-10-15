from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import httpx
from fastapi import FastAPI
from sqlalchemy import make_url

from catalog.application.ports import UnitOfWorkFactory
from catalog.domain.imports import DEFAULT_IMPORT_MAX_BYTES
from catalog.infra.memory import InMemoryStore, InMemoryUnitOfWork
from catalog.main import create_catalog_app
from catalog.settings import CatalogSettings, MediaSettings
from ecommerce_auth import JwtSettings, Role
from ecommerce_auth.testing import StubTokenIssuer, build_stub_verifier
from ecommerce_storage import InMemoryObjectStorage, ObjectStorage, S3Settings

SEEDED_CATEGORIES = (
    ("Books", "books"),
    ("Electronics", "electronics"),
    ("Home & Office", "home-office"),
)


class SteppingClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, minutes: int = 1) -> None:
        self.now += timedelta(minutes=minutes)


def seeded_store() -> InMemoryStore:
    store = InMemoryStore()
    store.seed_categories(*SEEDED_CATEGORIES)
    return store


SEEDED_PRODUCT_COUNT = 200_000
MEDIA_BASE_URL = "http://media.test/media"


def media_settings() -> MediaSettings:
    return MediaSettings(
        S3Settings("test-access", "test-secret", endpoint_url="http://127.0.0.1:1"),
        "media",
        MEDIA_BASE_URL,
    )


def build_test_app(
    issuer: StubTokenIssuer,
    unit_of_work: UnitOfWorkFactory,
    clock: SteppingClock | None = None,
    storage: ObjectStorage | None = None,
    imports_storage: ObjectStorage | None = None,
    import_max_bytes: int = DEFAULT_IMPORT_MAX_BYTES,
) -> FastAPI:
    settings = CatalogSettings(
        database_url=make_url("postgresql+asyncpg://unused:unused@127.0.0.1:1/unused"),
        jwt=JwtSettings(jwks_url="http://auth.test/jwks.json", issuer="ecommerce-auth"),
        media=media_settings(),
        import_max_bytes=import_max_bytes,
    )
    app = create_catalog_app(
        settings,
        unit_of_work=unit_of_work,
        clock=clock or SteppingClock(),
        storage=storage or InMemoryObjectStorage(MEDIA_BASE_URL),
        imports_storage=imports_storage or InMemoryObjectStorage(MEDIA_BASE_URL),
    )
    app.state.token_verifier = build_stub_verifier(issuer)
    return app


def in_memory_app(
    issuer: StubTokenIssuer,
    store: InMemoryStore,
    clock: SteppingClock | None = None,
    storage: ObjectStorage | None = None,
    imports_storage: ObjectStorage | None = None,
    import_max_bytes: int = DEFAULT_IMPORT_MAX_BYTES,
) -> FastAPI:
    return build_test_app(
        issuer,
        lambda: InMemoryUnitOfWork(store),
        clock,
        storage,
        imports_storage,
        import_max_bytes,
    )


@asynccontextmanager
async def http_client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def bearer(issuer: StubTokenIssuer, role: Role = Role.ADMIN) -> dict[str, str]:
    return {"Authorization": f"Bearer {issuer.issue(role=role)}"}


def valid_product(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "sku": "RS-001",
        "name": "Running Shoes",
        "description": "Lightweight running shoes",
        "price": "89.99",
        "stock": 150,
        "weight_kg": "0.35",
    }
    return body | overrides
