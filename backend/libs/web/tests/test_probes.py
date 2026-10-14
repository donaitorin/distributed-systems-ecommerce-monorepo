import asyncio
import json
from collections.abc import AsyncIterator

import httpx
import pytest

from ecommerce_web import PROBLEM_MEDIA_TYPE, ReadinessCheck, ServiceSettings, create_app


async def passing() -> None:
    return None


async def failing() -> None:
    raise ConnectionError("password=hunter2 refused")


async def hanging() -> None:
    await asyncio.sleep(10)


def client_for(*checks: ReadinessCheck, timeout: float = 0.2) -> httpx.AsyncClient:
    app = create_app(ServiceSettings(name="svc", readiness_timeout_seconds=timeout), checks)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.fixture
async def plain_client() -> AsyncIterator[httpx.AsyncClient]:
    async with client_for() as client:
        yield client


async def test_health_is_always_ok(plain_client: httpx.AsyncClient) -> None:
    response = await plain_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_health_ignores_failing_readiness_checks() -> None:
    async with client_for(ReadinessCheck("db", failing)) as client:
        response = await client.get("/health")

    assert response.status_code == 200


async def test_ready_without_checks_is_ready(plain_client: httpx.AsyncClient) -> None:
    response = await plain_client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {}}


async def test_ready_reports_every_passing_check() -> None:
    async with client_for(
        ReadinessCheck("db", passing), ReadinessCheck("kafka", passing)
    ) as client:
        response = await client.get("/ready")

    assert response.status_code == 200
    assert response.json()["checks"] == {"db": "ok", "kafka": "ok"}


async def test_ready_is_unavailable_when_a_check_fails() -> None:
    async with client_for(
        ReadinessCheck("db", failing), ReadinessCheck("kafka", passing)
    ) as client:
        response = await client.get("/ready")

    body = response.json()
    assert response.status_code == 503
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    assert body["status"] == 503
    assert body["title"] == "Service not ready"
    assert body["checks"] == {"db": "failed", "kafka": "ok"}


async def test_ready_does_not_leak_failure_details() -> None:
    async with client_for(ReadinessCheck("db", failing)) as client:
        response = await client.get("/ready")

    assert "hunter2" not in response.text


async def test_ready_times_out_a_hanging_check() -> None:
    async with client_for(ReadinessCheck("kafka", hanging), timeout=0.05) as client:
        response = await client.get("/ready")

    assert response.status_code == 503
    assert response.json()["checks"] == {"kafka": "timeout"}


async def test_checks_run_concurrently() -> None:
    first_started, second_started = asyncio.Event(), asyncio.Event()

    async def first() -> None:
        first_started.set()
        await second_started.wait()

    async def second() -> None:
        second_started.set()
        await first_started.wait()

    async with client_for(
        ReadinessCheck("first", first), ReadinessCheck("second", second), timeout=1
    ) as client:
        response = await client.get("/ready")

    assert response.status_code == 200


async def test_failed_check_is_logged_with_its_name(capsys: pytest.CaptureFixture[str]) -> None:
    async with client_for(ReadinessCheck("db", failing)) as client:
        await client.get("/ready")

    entries = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    failure = next(entry for entry in entries if entry["message"] == "readiness check failed")
    assert failure["check"] == "db"
    assert failure["service"] == "svc"
    assert "ConnectionError" in failure["exception"]
