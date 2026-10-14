import json
import logging

import httpx
import pytest

from ecommerce_auth import ManagedTokenVerifier
from ecommerce_auth.testing import StubTokenIssuer, build_stub_verifier
from ecommerce_observability import REQUEST_ID_HEADER
from ecommerce_web import ServiceSettings, create_app


async def test_responses_carry_a_generated_request_id() -> None:
    app = create_app(ServiceSettings(name="svc"))

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/health")

    assert response.headers[REQUEST_ID_HEADER]


async def test_application_logs_are_json_with_service_name_and_request_id(
    capsys: pytest.CaptureFixture[str],
) -> None:
    app = create_app(ServiceSettings(name="catalog", log_level="INFO"))

    @app.get("/log")
    async def log() -> dict[str, str]:
        logging.getLogger("catalog.api").info("handled")
        return {}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/log")

    entries = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    entry = next(entry for entry in entries if entry["logger"] == "catalog.api")
    assert entry["service"] == "catalog"
    assert entry["request_id"] == response.headers[REQUEST_ID_HEADER]


def test_service_metadata_is_exposed_in_the_openapi_document() -> None:
    app = create_app(ServiceSettings(name="catalog", version="2.3.4"))

    assert app.openapi()["info"] == {"title": "catalog", "version": "2.3.4"}


async def test_token_verifier_is_installed_and_closed_with_the_app() -> None:
    managed = ManagedTokenVerifier(build_stub_verifier(StubTokenIssuer()), httpx.AsyncClient())
    app = create_app(ServiceSettings(name="svc"), token_verifier=managed)

    async with app.router.lifespan_context(app):
        assert app.state.token_verifier is managed.verifier
        assert not managed.http_client.is_closed

    assert managed.http_client.is_closed


def test_app_without_a_verifier_has_none_installed() -> None:
    app = create_app(ServiceSettings(name="svc"))

    assert not hasattr(app.state, "token_verifier")


async def test_shutdown_hooks_run_when_the_app_stops() -> None:
    calls: list[str] = []

    async def dispose_engine() -> None:
        calls.append("engine")

    async def close_client() -> None:
        calls.append("client")

    app = create_app(ServiceSettings(name="svc"), on_shutdown=[dispose_engine, close_client])

    async with app.router.lifespan_context(app):
        assert calls == []

    assert sorted(calls) == ["client", "engine"]


async def test_a_failing_shutdown_hook_does_not_skip_the_others() -> None:
    calls: list[str] = []

    async def failing() -> None:
        raise RuntimeError("cannot dispose")

    async def healthy() -> None:
        calls.append("healthy")

    app = create_app(ServiceSettings(name="svc"), on_shutdown=[healthy, failing])

    with pytest.raises(RuntimeError, match="cannot dispose"):
        async with app.router.lifespan_context(app):
            pass

    assert calls == ["healthy"]


async def test_the_verifier_is_still_closed_when_a_hook_fails() -> None:
    managed = ManagedTokenVerifier(build_stub_verifier(StubTokenIssuer()), httpx.AsyncClient())

    async def failing() -> None:
        raise RuntimeError("cannot dispose")

    app = create_app(ServiceSettings(name="svc"), token_verifier=managed, on_shutdown=[failing])

    with pytest.raises(RuntimeError):
        async with app.router.lifespan_context(app):
            pass

    assert managed.http_client.is_closed


async def test_root_path_is_applied_to_the_openapi_servers() -> None:
    app = create_app(ServiceSettings(name="svc"), root_path="/catalog")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/openapi.json")

    assert response.json()["servers"] == [{"url": "/catalog"}]
