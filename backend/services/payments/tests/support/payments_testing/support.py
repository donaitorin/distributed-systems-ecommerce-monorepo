from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

import httpx
from fastapi import FastAPI
from sqlalchemy import make_url

from ecommerce_auth import JwtSettings, Role
from ecommerce_auth.testing import StubTokenIssuer, build_stub_verifier
from payments.application.ports import UnitOfWorkFactory
from payments.infra.memory import InMemoryStore, InMemoryUnitOfWork
from payments.main import create_payments_app
from payments.settings import PaymentsSettings
from payments_testing.data import CUSTOMER

UNUSED_DATABASE = "postgresql+asyncpg://unused:unused@127.0.0.1:1/unused"


def payments_settings(**overrides: Any) -> PaymentsSettings:
    values: dict[str, Any] = {
        "database_url": make_url(UNUSED_DATABASE),
        "jwt": JwtSettings(jwks_url="http://auth.test/jwks.json", issuer="ecommerce-auth"),
    }
    return PaymentsSettings(**(values | overrides))


def build_test_app(issuer: StubTokenIssuer, unit_of_work: UnitOfWorkFactory) -> FastAPI:
    app = create_payments_app(payments_settings(), unit_of_work=unit_of_work)
    app.state.token_verifier = build_stub_verifier(issuer)
    return app


def in_memory_app(issuer: StubTokenIssuer, store: InMemoryStore) -> FastAPI:
    return build_test_app(issuer, lambda: InMemoryUnitOfWork(store))


@asynccontextmanager
async def http_client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def bearer(
    issuer: StubTokenIssuer, user_id: UUID = CUSTOMER, role: Role = Role.CUSTOMER
) -> dict[str, str]:
    return {"Authorization": f"Bearer {issuer.issue(subject=str(user_id), role=role)}"}
