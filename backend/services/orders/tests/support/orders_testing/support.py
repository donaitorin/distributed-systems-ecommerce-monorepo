from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

import httpx
from fastapi import FastAPI
from sqlalchemy import make_url

from ecommerce_auth import JwtSettings, Role
from ecommerce_auth.testing import StubTokenIssuer, build_stub_verifier
from orders.application.ports import UnitOfWorkFactory
from orders.infra.memory import InMemoryStore, InMemoryUnitOfWork
from orders.main import create_orders_app
from orders.settings import OrdersSettings
from orders_testing.data import CUSTOMER, SteppingClock

UNUSED_DATABASE = "postgresql+asyncpg://unused:unused@127.0.0.1:1/unused"


def orders_settings(**overrides: Any) -> OrdersSettings:
    values: dict[str, Any] = {
        "database_url": make_url(UNUSED_DATABASE),
        "jwt": JwtSettings(jwks_url="http://auth.test/jwks.json", issuer="ecommerce-auth"),
    }
    return OrdersSettings(**(values | overrides))


def build_test_app(
    issuer: StubTokenIssuer, unit_of_work: UnitOfWorkFactory, clock: SteppingClock | None = None
) -> FastAPI:
    app = create_orders_app(
        orders_settings(), unit_of_work=unit_of_work, clock=clock or SteppingClock()
    )
    app.state.token_verifier = build_stub_verifier(issuer)
    return app


def in_memory_app(
    issuer: StubTokenIssuer, store: InMemoryStore, clock: SteppingClock | None = None
) -> FastAPI:
    return build_test_app(issuer, lambda: InMemoryUnitOfWork(store), clock)


@asynccontextmanager
async def http_client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def bearer(
    issuer: StubTokenIssuer, user_id: UUID = CUSTOMER, role: Role = Role.CUSTOMER
) -> dict[str, str]:
    return {"Authorization": f"Bearer {issuer.issue(subject=str(user_id), role=role)}"}
