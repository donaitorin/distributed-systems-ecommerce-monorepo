import io
import json
import logging
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from types import TracebackType
from typing import Self

import httpx
import pytest
from catalog_testing.support import build_test_app, http_client

from catalog.application.errors import SearchTimeoutError
from ecommerce_auth.testing import StubTokenIssuer
from ecommerce_observability import JsonFormatter

REQUEST_ID = "5b1c1a74-6c1d-4a63-9a5e-2f0f6f4d9c11"


class TimingOutProducts:
    async def search(self, *args: object) -> object:
        raise SearchTimeoutError(2000)


class TimingOutUnitOfWork:
    products = TimingOutProducts()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None


@pytest.fixture
async def timing_out_client(issuer: StubTokenIssuer) -> AsyncIterator[httpx.AsyncClient]:
    app = build_test_app(issuer, lambda: TimingOutUnitOfWork())  # type: ignore[arg-type, return-value]
    async with http_client(app) as client:
        yield client


@contextmanager
def captured_json_logs() -> Iterator[io.StringIO]:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter("catalog"))
    logger = logging.getLogger("catalog.api.errors")
    logger.addHandler(handler)
    previous_level = logger.level
    logger.setLevel(logging.WARNING)
    try:
        yield stream
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)


async def test_a_search_timeout_is_a_503_problem_with_retry_after(
    timing_out_client: httpx.AsyncClient,
) -> None:
    response = await timing_out_client.get("/api/v1/products", params={"q": "shoes"})

    body = response.json()
    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.headers["Retry-After"] == "1"
    assert body["title"] == "Search timed out"
    assert body["status"] == 503
    assert "2000 ms" in body["detail"]
    assert body["instance"] == "/api/v1/products"


async def test_a_search_timeout_is_logged_with_the_request_id(
    timing_out_client: httpx.AsyncClient,
) -> None:
    with captured_json_logs() as stream:
        response = await timing_out_client.get(
            "/api/v1/products", params={"q": "shoes"}, headers={"X-Request-ID": REQUEST_ID}
        )

    entry = json.loads(stream.getvalue().strip().splitlines()[-1])
    assert response.json()["request_id"] == REQUEST_ID
    assert response.headers["X-Request-ID"] == REQUEST_ID
    assert entry["level"] == "WARNING"
    assert entry["message"] == "search timed out"
    assert entry["request_id"] == REQUEST_ID
    assert entry["timeout_ms"] == 2000
    assert entry["path"] == "/api/v1/products"
    assert "shoes" not in json.dumps(entry)


async def test_the_openapi_document_lists_the_503_response(
    timing_out_client: httpx.AsyncClient,
) -> None:
    document = (await timing_out_client.get("/openapi.json")).json()

    responses = document["paths"]["/api/v1/products"]["get"]["responses"]
    assert "503" in responses
