from collections.abc import AsyncIterator
from uuid import UUID

import httpx
import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import Message, Receive, Scope, Send

from ecommerce_observability import (
    REQUEST_ID_HEADER,
    RequestIdMiddleware,
    get_request_id,
    resolve_request_id,
)


async def echo_request_id(request: Request) -> JSONResponse:
    return JSONResponse(
        {"request_id": get_request_id(), "state_request_id": request.state.request_id}
    )


def build_app() -> Starlette:
    app = Starlette(routes=[Route("/", echo_request_id)])
    app.add_middleware(RequestIdMiddleware)
    return app


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=build_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


async def test_generates_request_id_when_missing(client: httpx.AsyncClient) -> None:
    response = await client.get("/")

    generated = response.headers[REQUEST_ID_HEADER]
    assert UUID(generated)
    assert response.json() == {"request_id": generated, "state_request_id": generated}


async def test_propagates_valid_incoming_request_id(client: httpx.AsyncClient) -> None:
    incoming = "0c5a9d86-2c8e-4d7e-a0a3-5b6c1b8f2d44"

    response = await client.get("/", headers={REQUEST_ID_HEADER: incoming})

    assert response.headers[REQUEST_ID_HEADER] == incoming
    assert response.json() == {"request_id": incoming, "state_request_id": incoming}


async def test_replaces_invalid_incoming_request_id(client: httpx.AsyncClient) -> None:
    response = await client.get("/", headers={REQUEST_ID_HEADER: "not-a-uuid\tinjected"})

    replaced = response.headers[REQUEST_ID_HEADER]
    assert UUID(replaced)
    assert response.json() == {"request_id": replaced, "state_request_id": replaced}


async def test_each_request_gets_its_own_id(client: httpx.AsyncClient) -> None:
    first = await client.get("/")
    second = await client.get("/")

    assert first.headers[REQUEST_ID_HEADER] != second.headers[REQUEST_ID_HEADER]


async def test_request_id_is_cleared_after_the_request(client: httpx.AsyncClient) -> None:
    await client.get("/")

    assert get_request_id() is None


async def test_non_http_scopes_pass_through_untouched() -> None:
    seen: list[str] = []

    async def inner(scope: Scope, receive: Receive, send: Send) -> None:
        seen.append(scope["type"])

    async def receive() -> Message:
        return {"type": "lifespan.startup"}

    async def send(message: Message) -> None:
        return None

    await RequestIdMiddleware(inner)({"type": "lifespan"}, receive, send)

    assert seen == ["lifespan"]
    assert get_request_id() is None


def test_resolve_request_id_normalizes_valid_uuid_casing() -> None:
    assert resolve_request_id("0C5A9D86-2C8E-4D7E-A0A3-5B6C1B8F2D44") == (
        "0c5a9d86-2c8e-4d7e-a0a3-5b6c1b8f2d44"
    )


def test_resolve_request_id_generates_when_none() -> None:
    assert UUID(resolve_request_id(None))
