import contextlib
from collections.abc import Callable

import httpx
import pytest
from cart_testing.support import IMAGE_KEY

from cart.application.errors import CatalogCircuitOpenError, CatalogUnavailableError
from cart.infra.catalog_client import HttpCatalogGateway
from ecommerce_resilience import (
    BreakerConfig,
    CircuitBreaker,
    CircuitState,
    ReadRetryPolicy,
)

BODY = {
    "sku": "RS-001",
    "name": "Running Shoes",
    "price": "89.99",
    "stock": 12,
    "version": 4,
    "image_url": f"/media/{IMAGE_KEY}-1200.webp",
}
THRESHOLD = 3
OPEN_SECONDS = 10.0


class Clock:
    def __init__(self) -> None:
        self.now = 500.0

    def __call__(self) -> float:
        return self.now


class Calls:
    def __init__(self, behaviour: Callable[[httpx.Request], httpx.Response]) -> None:
        self.behaviour = behaviour
        self.requests: list[httpx.Request] = []
        self.pauses: list[float] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.behaviour(request)

    async def sleep(self, seconds: float) -> None:
        self.pauses.append(seconds)


class Setup:
    def __init__(self, behaviour: Callable[[httpx.Request], httpx.Response], attempts: int) -> None:
        self.calls = Calls(behaviour)
        self.clock = Clock()
        self.breaker = CircuitBreaker(
            "catalog", BreakerConfig(THRESHOLD, OPEN_SECONDS, 1), clock=self.clock
        )
        client = httpx.AsyncClient(
            base_url="http://catalog.test", transport=httpx.MockTransport(self.calls.handler)
        )
        self.gateway = HttpCatalogGateway(
            client,
            "/media",
            self.breaker,
            ReadRetryPolicy(attempts=attempts, initial_delay_seconds=0.01, max_delay_seconds=0.02),
            self.calls.sleep,
        )

    @property
    def state(self) -> CircuitState:
        return self.breaker.state


def down(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("refused", request=request)


def healthy(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json=BODY)


async def test_a_transport_error_is_retried_once_and_then_succeeds() -> None:
    attempts = iter([down, healthy])
    setup = Setup(lambda request: next(attempts)(request), attempts=2)

    product = await setup.gateway.get("RS-001")

    assert product is not None
    assert len(setup.calls.requests) == 2
    assert len(setup.calls.pauses) == 1


@pytest.mark.parametrize("status", [502, 503, 504])
async def test_a_gateway_error_status_is_retried(status: int) -> None:
    setup = Setup(lambda request: httpx.Response(status), attempts=3)

    with pytest.raises(CatalogUnavailableError):
        await setup.gateway.get("RS-001")

    assert len(setup.calls.requests) == 3


async def test_a_read_timeout_is_not_retried_so_the_caller_is_not_kept_waiting() -> None:
    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("no answer", request=request)

    setup = Setup(slow, attempts=3)

    with pytest.raises(CatalogUnavailableError):
        await setup.gateway.get("RS-001")

    assert len(setup.calls.requests) == 1


async def test_a_connect_timeout_is_retried() -> None:
    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("no route", request=request)

    setup = Setup(unreachable, attempts=2)

    with pytest.raises(CatalogUnavailableError):
        await setup.gateway.get("RS-001")

    assert len(setup.calls.requests) == 2


@pytest.mark.parametrize("status", [404, 500, 429, 401, 400])
async def test_other_answers_are_not_retried(status: int) -> None:
    setup = Setup(lambda request: httpx.Response(status, json={}), attempts=3)

    with contextlib.suppress(CatalogUnavailableError):
        await setup.gateway.get("RS-001")

    assert len(setup.calls.requests) == 1
    assert setup.calls.pauses == []


async def test_only_get_requests_are_ever_sent() -> None:
    setup = Setup(down, attempts=3)

    with pytest.raises(CatalogUnavailableError):
        await setup.gateway.get("RS-001")

    assert {request.method for request in setup.calls.requests} == {"GET"}


async def test_a_missing_product_does_not_count_against_the_breaker() -> None:
    setup = Setup(lambda request: httpx.Response(404), attempts=1)

    for _ in range(THRESHOLD * 2):
        assert await setup.gateway.get("NOPE-1") is None

    assert setup.state is CircuitState.CLOSED


@pytest.mark.parametrize("status", [401, 403, 400])
async def test_a_client_error_does_not_trip_the_breaker(status: int) -> None:
    setup = Setup(lambda request: httpx.Response(status), attempts=1)

    for _ in range(THRESHOLD * 2):
        with pytest.raises(CatalogUnavailableError):
            await setup.gateway.get("RS-001")

    assert setup.state is CircuitState.CLOSED


@pytest.mark.parametrize("status", [500, 502, 503, 429])
async def test_server_errors_trip_the_breaker(status: int) -> None:
    setup = Setup(lambda request: httpx.Response(status), attempts=1)

    for _ in range(THRESHOLD):
        with pytest.raises(CatalogUnavailableError):
            await setup.gateway.get("RS-001")

    assert setup.state is CircuitState.OPEN


async def test_a_logical_call_that_used_its_retries_counts_as_one_failure() -> None:
    setup = Setup(down, attempts=2)

    for _ in range(THRESHOLD - 1):
        with pytest.raises(CatalogUnavailableError):
            await setup.gateway.get("RS-001")

    assert setup.state is CircuitState.CLOSED
    assert len(setup.calls.requests) == (THRESHOLD - 1) * 2


async def test_an_open_circuit_answers_without_calling_catalog() -> None:
    setup = Setup(down, attempts=1)
    for _ in range(THRESHOLD):
        with pytest.raises(CatalogUnavailableError):
            await setup.gateway.get("RS-001")
    sent = len(setup.calls.requests)
    setup.clock.now += 4.0

    with pytest.raises(CatalogCircuitOpenError) as rejected:
        await setup.gateway.get("RS-001")

    assert len(setup.calls.requests) == sent
    assert rejected.value.retry_after_seconds == 6


async def test_the_circuit_recovers_when_catalog_answers_the_probe() -> None:
    state = {"up": False}

    def behaviour(request: httpx.Request) -> httpx.Response:
        return healthy(request) if state["up"] else down(request)

    setup = Setup(behaviour, attempts=1)
    for _ in range(THRESHOLD):
        with pytest.raises(CatalogUnavailableError):
            await setup.gateway.get("RS-001")
    state["up"] = True
    setup.clock.now += OPEN_SECONDS

    assert await setup.gateway.get("RS-001") is not None

    assert setup.state is CircuitState.CLOSED


async def test_a_failed_probe_keeps_the_circuit_open() -> None:
    setup = Setup(down, attempts=1)
    for _ in range(THRESHOLD):
        with pytest.raises(CatalogUnavailableError):
            await setup.gateway.get("RS-001")
    setup.clock.now += OPEN_SECONDS

    with pytest.raises(CatalogUnavailableError):
        await setup.gateway.get("RS-001")

    assert setup.state is CircuitState.OPEN
    with pytest.raises(CatalogCircuitOpenError):
        await setup.gateway.get("RS-001")
