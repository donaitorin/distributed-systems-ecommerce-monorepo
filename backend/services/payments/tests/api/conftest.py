from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI
from payments_testing.support import http_client, in_memory_app

from ecommerce_auth.testing import StubTokenIssuer
from payments.infra.memory import InMemoryStore


@pytest.fixture(scope="session")
def issuer() -> StubTokenIssuer:
    return StubTokenIssuer()


@pytest.fixture
def app(issuer: StubTokenIssuer, store: InMemoryStore) -> FastAPI:
    return in_memory_app(issuer, store)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with http_client(app) as http:
        yield http
