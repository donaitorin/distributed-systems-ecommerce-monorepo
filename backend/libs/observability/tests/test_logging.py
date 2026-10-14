import json
import logging
import sys
from collections.abc import Iterator

import httpx
import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from ecommerce_observability import (
    REQUEST_ID_HEADER,
    JsonFormatter,
    RequestIdMiddleware,
    configure_logging,
    get_request_id,
)


@pytest.fixture(autouse=True)
def restore_root_logger() -> Iterator[None]:
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    yield
    root.handlers, root.level = handlers, level


def make_record(message: str = "hello", **extra: object) -> logging.LogRecord:
    record = logging.LogRecord(
        name="orders",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg=message,
        args=(),
        exc_info=None,
    )
    record.__dict__.update(extra)
    return record


def test_formats_a_single_json_line_with_core_fields() -> None:
    line = JsonFormatter("catalog").format(make_record("stock reserved"))

    entry = json.loads(line)
    assert "\n" not in line
    assert entry["message"] == "stock reserved"
    assert entry["level"] == "INFO"
    assert entry["logger"] == "orders"
    assert entry["service"] == "catalog"
    assert entry["timestamp"].endswith("+00:00")
    assert "request_id" not in entry


def test_includes_extra_fields() -> None:
    entry = json.loads(JsonFormatter("catalog").format(make_record(order_id="o-1")))

    assert entry["order_id"] == "o-1"


def test_serializes_non_json_values_as_strings() -> None:
    entry = json.loads(JsonFormatter("catalog").format(make_record(value={1, 2})))

    assert isinstance(entry["value"], str)


def test_includes_exception_details() -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        record = make_record("failed")
        record.exc_info = sys.exc_info()

    entry = json.loads(JsonFormatter("catalog").format(record))

    assert "ValueError: boom" in entry["exception"]


def test_configure_logging_emits_json_to_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("cart", level="DEBUG")

    logging.getLogger("cart.test").debug("cart updated")

    entry = json.loads(capsys.readouterr().out)
    assert entry["service"] == "cart"
    assert entry["message"] == "cart updated"


def test_configure_logging_replaces_existing_handlers() -> None:
    configure_logging("cart")
    configure_logging("cart")

    assert len(logging.getLogger().handlers) == 1


async def test_request_id_reaches_logs_and_response(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("catalog")

    async def handler(request: Request) -> PlainTextResponse:
        logging.getLogger("catalog.api").info("handling")
        return PlainTextResponse("ok")

    app = Starlette(routes=[Route("/", handler)])
    app.add_middleware(RequestIdMiddleware)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/")

    entries = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    entry = next(entry for entry in entries if entry["logger"] == "catalog.api")
    assert entry["request_id"] == response.headers[REQUEST_ID_HEADER]
    assert get_request_id() is None
