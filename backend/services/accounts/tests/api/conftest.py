from collections.abc import AsyncIterator

import httpx
import pytest
from accounts_testing.data import SteppingClock
from accounts_testing.support import http_client, in_memory_app
from fastapi import FastAPI

from accounts.infra.memory import InMemoryStore
from ecommerce_auth.testing import StubTokenIssuer


@pytest.fixture(scope="session")
def issuer() -> StubTokenIssuer:
    return StubTokenIssuer()


@pytest.fixture
def app(issuer: StubTokenIssuer, store: InMemoryStore, clock: SteppingClock) -> FastAPI:
    return in_memory_app(issuer, store, clock)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with http_client(app) as http:
        yield http
