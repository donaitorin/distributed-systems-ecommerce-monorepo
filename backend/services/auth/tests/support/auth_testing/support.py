from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from sqlalchemy import make_url

from auth.application.ports import PasswordHasher, UnitOfWorkFactory
from auth.infra.hashing import HashingSettings
from auth.infra.keys import KeyStore, SigningKey, signing_key_from
from auth.main import create_auth_app
from auth.settings import AuthSettings
from ecommerce_auth import JwtSettings, TokenVerifier
from ecommerce_auth.jwks import JwksClient

UNUSED_DATABASE = "postgresql+asyncpg://unused:unused@127.0.0.1:1/unused"
ISSUER = "ecommerce-auth"
AUDIENCE = "ecommerce-api"
STRONG_PASSWORD = "correct horse battery"
FAST_HASHING = HashingSettings(memory_cost_kib=8, time_cost=1, parallelism=1)


class SteppingClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float = 0, days: float = 0) -> None:
        self.now += timedelta(seconds=seconds, days=days)


class FakeHasher:
    def __init__(self) -> None:
        self.decoy_calls = 0
        self.rehash_needed = False
        self.hash_calls = 0

    async def hash(self, password: str) -> str:
        self.hash_calls += 1
        return f"fake${password}"

    async def verify(self, password_hash: str, password: str) -> bool:
        return password_hash == f"fake${password}"

    async def verify_decoy(self, password: str) -> None:
        self.decoy_calls += 1

    def needs_rehash(self, password_hash: str) -> bool:
        return self.rehash_needed and password_hash.startswith("fake$")


def new_signing_key() -> SigningKey:
    return signing_key_from(rsa.generate_private_key(public_exponent=65537, key_size=2048))


def auth_settings(**overrides: Any) -> AuthSettings:
    values: dict[str, Any] = {
        "database_url": make_url(UNUSED_DATABASE),
        "issuer": ISSUER,
        "audience": AUDIENCE,
        "hashing": FAST_HASHING,
    }
    return AuthSettings(**(values | overrides))


def build_test_app(
    unit_of_work: UnitOfWorkFactory,
    keys: KeyStore,
    clock: SteppingClock,
    hasher: PasswordHasher | None = None,
    **settings_overrides: Any,
) -> FastAPI:
    return create_auth_app(
        auth_settings(**settings_overrides),
        unit_of_work=unit_of_work,
        clock=clock,
        keys=keys,
        hasher=hasher or FakeHasher(),
    )


def verifier_for(jwks_document: dict[str, Any]) -> TokenVerifier:
    settings = JwtSettings(jwks_url="http://auth.test/jwks.json", issuer=ISSUER, audience=AUDIENCE)
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=jwks_document))
    return TokenVerifier(settings, JwksClient(settings, httpx.AsyncClient(transport=transport)))


@asynccontextmanager
async def http_client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def register_user(
    client: httpx.AsyncClient, email: str = "ada@example.com", password: str = STRONG_PASSWORD
) -> httpx.Response:
    return await client.post("/api/v1/auth/register", json={"email": email, "password": password})


async def login_user(
    client: httpx.AsyncClient, email: str = "ada@example.com", password: str = STRONG_PASSWORD
) -> httpx.Response:
    return await client.post("/api/v1/auth/login", json={"email": email, "password": password})


async def refresh_with(client: httpx.AsyncClient, refresh_token: str) -> httpx.Response:
    return await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})


async def patch_role(
    client: httpx.AsyncClient, user_id: object, role: str, token: str | None = None
) -> httpx.Response:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return await client.patch(
        f"/api/v1/auth/users/{user_id}/role", json={"role": role}, headers=headers
    )
