from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI
from sqlalchemy import make_url

from accounts.application.ports import UnitOfWorkFactory
from accounts.infra.memory import InMemoryStore, InMemoryUnitOfWork
from accounts.main import create_accounts_app
from accounts.settings import AccountsSettings
from accounts_testing.data import SteppingClock
from ecommerce_auth import JwtSettings, Role
from ecommerce_auth.testing import StubTokenIssuer, build_stub_verifier

UNUSED_DATABASE = "postgresql+asyncpg://unused:unused@127.0.0.1:1/unused"


def accounts_settings(**overrides: Any) -> AccountsSettings:
    values: dict[str, Any] = {
        "database_url": make_url(UNUSED_DATABASE),
        "jwt": JwtSettings(jwks_url="http://auth.test/jwks.json", issuer="ecommerce-auth"),
    }
    return AccountsSettings(**(values | overrides))


def build_test_app(
    issuer: StubTokenIssuer, unit_of_work: UnitOfWorkFactory, clock: SteppingClock | None = None
) -> FastAPI:
    app = create_accounts_app(
        accounts_settings(), unit_of_work=unit_of_work, clock=clock or SteppingClock()
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
    issuer: StubTokenIssuer,
    user_id: UUID | None = None,
    role: Role = Role.CUSTOMER,
    email: str | None = "ada@example.com",
    **claims: Any,
) -> dict[str, str]:
    extra = dict(claims) | ({"email": email} if email is not None else {})
    token = issuer.issue(subject=str(user_id or uuid4()), role=role, **extra)
    return {"Authorization": f"Bearer {token}"}
