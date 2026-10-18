import asyncio
import socket
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field

import httpx
import pytest
import uvicorn
from cart_testing.support import SteppingClock, Stores, bearer, cart_settings, http_client
from fastapi import FastAPI

from cart.main import create_cart_app
from ecommerce_auth.testing import StubTokenIssuer, build_stub_verifier
from ecommerce_resilience import BreakerConfig

THRESHOLD = 3
OPEN_SECONDS = 1.5
CATALOG_TIMEOUT_SECONDS = 0.5
FAST_SECONDS = 0.25
POLL_SECONDS = 0.1
START_POLLS = 100
RECOVERY_POLLS = 150
ITEM = "/api/v1/cart/items/{sku}"


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def catalog_app() -> FastAPI:
    app = FastAPI()

    @app.get("/api/v1/products/{sku}")
    async def read(sku: str) -> dict[str, object]:
        return {
            "sku": sku,
            "name": "Running Shoes",
            "price": "89.99",
            "stock": 10,
            "version": 1,
            "image_url": None,
        }

    return app


@dataclass(slots=True)
class StandInCatalog:
    port: int
    server: uvicorn.Server | None = None
    task: asyncio.Task[None] | None = None
    blackhole: asyncio.Server | None = None
    held: list[asyncio.StreamWriter] = field(default_factory=list)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    async def start(self) -> None:
        config = uvicorn.Config(
            catalog_app(), host="127.0.0.1", port=self.port, log_level="warning", lifespan="off"
        )
        self.server = uvicorn.Server(config)
        self.task = asyncio.create_task(self.server.serve())
        for _ in range(START_POLLS):
            if self.server.started:
                return
            await asyncio.sleep(POLL_SECONDS)
        raise TimeoutError("the stand-in catalog did not start")

    async def stop(self) -> None:
        if self.server is not None and self.task is not None:
            self.server.should_exit = True
            await asyncio.wait_for(self.task, timeout=10)
            self.server = self.task = None

    async def hang(self) -> None:
        async def accept_and_stay_silent(
            reader: asyncio.StreamReader, writer: asyncio.StreamWriter
        ) -> None:
            self.held.append(writer)
            with suppress(ConnectionError):
                await reader.read()

        self.blackhole = await asyncio.start_server(
            accept_and_stay_silent, "127.0.0.1", self.port, reuse_address=True
        )

    async def release(self) -> None:
        if self.blackhole is not None:
            self.blackhole.close()
            for writer in self.held:
                writer.close()
            self.held.clear()
            await asyncio.wait_for(self.blackhole.wait_closed(), timeout=10)
            self.blackhole = None


@asynccontextmanager
async def cart_against(
    catalog: StandInCatalog, issuer: StubTokenIssuer
) -> AsyncIterator[httpx.AsyncClient]:
    app = create_cart_app(
        cart_settings(
            catalog_base_url=catalog.base_url,
            catalog_timeout_seconds=CATALOG_TIMEOUT_SECONDS,
            catalog_breaker=BreakerConfig(THRESHOLD, OPEN_SECONDS, 1),
        ),
        store=(stores := Stores()).carts,
        projection=stores.projection,
        clock=SteppingClock(),
    )
    app.state.token_verifier = build_stub_verifier(issuer)
    async with http_client(app) as http:
        yield http


@pytest.fixture
async def catalog() -> AsyncIterator[StandInCatalog]:
    stand_in = StandInCatalog(free_port())
    yield stand_in
    await stand_in.stop()
    await stand_in.release()


async def add(client: httpx.AsyncClient, headers: dict[str, str], sku: str) -> httpx.Response:
    return await client.put(ITEM.format(sku=sku), json={"quantity": 1}, headers=headers)


async def timed(client: httpx.AsyncClient, headers: dict[str, str], sku: str) -> tuple[int, float]:
    started = time.monotonic()
    response = await add(client, headers, sku)
    return response.status_code, time.monotonic() - started


async def wait_until_adding_works(client: httpx.AsyncClient, headers: dict[str, str]) -> None:
    for attempt in range(RECOVERY_POLLS):
        if (await add(client, headers, f"PROBE-{attempt}")).status_code == 200:
            return
        await asyncio.sleep(POLL_SECONDS)
    raise TimeoutError("adding to the cart did not recover")


async def test_with_catalog_stopped_adding_fails_fast_once_open_and_recovers(
    catalog: StandInCatalog, issuer: StubTokenIssuer
) -> None:
    headers = bearer(issuer)
    await catalog.start()
    async with cart_against(catalog, issuer) as client:
        assert (await add(client, headers, "RS-001")).status_code == 200

        await catalog.stop()
        for number in range(THRESHOLD):
            assert (await add(client, headers, f"NEW-{number}")).status_code == 503
        status, elapsed = await timed(client, headers, "NEW-9")
        shown = await client.get("/api/v1/cart", headers=headers)

        assert (status, elapsed < FAST_SECONDS) == (503, True)
        assert (await add(client, headers, "NEW-9")).headers["retry-after"] in {"1", "2"}
        assert [line["sku"] for line in shown.json()["items"]] == ["RS-001"]

        await catalog.start()
        await wait_until_adding_works(client, headers)
        assert (await add(client, headers, "RS-002")).status_code == 200


async def test_with_catalog_hanging_the_breaker_replaces_the_timeout_with_an_instant_answer(
    catalog: StandInCatalog, issuer: StubTokenIssuer
) -> None:
    headers = bearer(issuer)
    await catalog.hang()
    async with cart_against(catalog, issuer) as client:
        slow = [await timed(client, headers, f"NEW-{number}") for number in range(THRESHOLD)]
        status, elapsed = await timed(client, headers, "NEW-9")

        assert all(code == 503 and took >= CATALOG_TIMEOUT_SECONDS for code, took in slow)
        assert (status, elapsed < FAST_SECONDS) == (503, True)

        await catalog.release()
        await catalog.start()
        await wait_until_adding_works(client, headers)
