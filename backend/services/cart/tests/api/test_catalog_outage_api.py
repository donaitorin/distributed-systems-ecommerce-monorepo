from collections.abc import AsyncIterator

import httpx
import pytest
from cart_testing.support import (
    SteppingClock,
    Stores,
    bearer,
    cart_settings,
    http_client,
)
from fastapi import FastAPI

from cart.infra.catalog_client import CIRCUIT_NAME, HttpCatalogGateway
from cart.main import create_cart_app
from ecommerce_auth.testing import StubTokenIssuer, build_stub_verifier
from ecommerce_resilience import BreakerConfig, CircuitBreaker, ReadRetryPolicy

CART = "/api/v1/cart"
THRESHOLD = 2
OPEN_SECONDS = 5.0
CATALOG_BODY = {
    "sku": "RS-001",
    "name": "Running Shoes",
    "price": "89.99",
    "stock": 10,
    "version": 1,
    "image_url": None,
}


class Catalog:
    def __init__(self) -> None:
        self.up = True
        self.requests = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests += 1
        if not self.up:
            raise httpx.ConnectError("refused", request=request)
        sku = request.url.path.rsplit("/", 1)[-1]
        return httpx.Response(200, json=CATALOG_BODY | {"sku": sku})


class Time:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


class Pauses:
    async def __call__(self, seconds: float) -> None:
        return None


@pytest.fixture
def catalog() -> Catalog:
    return Catalog()


@pytest.fixture
def time() -> Time:
    return Time()


@pytest.fixture
def stores() -> Stores:
    return Stores()


@pytest.fixture
async def client(
    issuer: StubTokenIssuer, catalog: Catalog, time: Time, stores: Stores
) -> AsyncIterator[httpx.AsyncClient]:
    upstream = httpx.AsyncClient(
        base_url="http://catalog.test", transport=httpx.MockTransport(catalog.handler)
    )
    gateway = HttpCatalogGateway(
        upstream,
        "/media",
        CircuitBreaker(CIRCUIT_NAME, BreakerConfig(THRESHOLD, OPEN_SECONDS, 1), clock=time),
        ReadRetryPolicy(attempts=1),
        Pauses(),
    )
    app: FastAPI = create_cart_app(
        cart_settings(),
        store=stores.carts,
        projection=stores.projection,
        catalog=gateway,
        clock=SteppingClock(),
    )
    app.state.token_verifier = build_stub_verifier(issuer)
    async with http_client(app) as http:
        yield http


@pytest.fixture
def customer(issuer: StubTokenIssuer) -> dict[str, str]:
    return bearer(issuer)


def item(sku: str) -> str:
    return f"{CART}/items/{sku}"


async def trip(client: httpx.AsyncClient, customer: dict[str, str], catalog: Catalog) -> None:
    catalog.up = False
    for number in range(THRESHOLD):
        response = await client.put(item(f"NEW-{number}"), json={"quantity": 1}, headers=customer)
        assert response.status_code == 503


async def test_the_first_failures_reach_catalog_and_report_an_outage(
    client: httpx.AsyncClient, customer: dict[str, str], catalog: Catalog
) -> None:
    catalog.up = False

    response = await client.put(item("NEW-1"), json={"quantity": 1}, headers=customer)

    assert response.status_code == 503
    assert response.headers["retry-after"] == "2"
    assert catalog.requests == 1


async def test_an_open_circuit_answers_fast_with_a_problem_and_retry_after(
    client: httpx.AsyncClient, customer: dict[str, str], catalog: Catalog, time: Time
) -> None:
    await trip(client, customer, catalog)
    sent = catalog.requests
    time.now += 2.0

    response = await client.put(item("NEW-9"), json={"quantity": 1}, headers=customer)

    assert catalog.requests == sent
    assert response.status_code == 503
    assert response.headers["content-type"] == "application/problem+json"
    assert response.headers["retry-after"] == "3"
    body = response.json()
    assert (body["title"], body["status"], body["code"]) == (
        "Catalog unavailable",
        503,
        "catalog_unavailable",
    )


async def test_an_existing_cart_can_still_be_read_and_adjusted_while_the_circuit_is_open(
    client: httpx.AsyncClient, customer: dict[str, str], catalog: Catalog
) -> None:
    assert (
        await client.put(item("RS-001"), json={"quantity": 1}, headers=customer)
    ).status_code == 200
    await trip(client, customer, catalog)
    sent = catalog.requests

    shown = await client.get(CART, headers=customer)
    adjusted = await client.put(item("RS-001"), json={"quantity": 3}, headers=customer)
    removed = await client.delete(item("RS-001"), headers=customer)

    assert shown.status_code == 200
    assert [line["sku"] for line in shown.json()["items"]] == ["RS-001"]
    assert adjusted.status_code == 200
    assert adjusted.json()["items"][0]["quantity"] == 3
    assert removed.status_code == 200
    assert catalog.requests == sent


async def test_adding_works_again_after_the_open_duration_once_catalog_is_back(
    client: httpx.AsyncClient, customer: dict[str, str], catalog: Catalog, time: Time
) -> None:
    await trip(client, customer, catalog)
    catalog.up = True
    time.now += OPEN_SECONDS

    response = await client.put(item("RS-001"), json={"quantity": 2}, headers=customer)

    assert response.status_code == 200
    assert (
        await client.put(item("RS-002"), json={"quantity": 1}, headers=customer)
    ).status_code == 200


async def test_a_catalog_that_is_still_down_after_the_open_duration_opens_it_again(
    client: httpx.AsyncClient, customer: dict[str, str], catalog: Catalog, time: Time
) -> None:
    await trip(client, customer, catalog)
    time.now += OPEN_SECONDS
    sent = catalog.requests

    probe = await client.put(item("NEW-7"), json={"quantity": 1}, headers=customer)
    rejected = await client.put(item("NEW-8"), json={"quantity": 1}, headers=customer)

    assert probe.status_code == rejected.status_code == 503
    assert catalog.requests == sent + 1
    assert rejected.headers["retry-after"] == str(int(OPEN_SECONDS))
