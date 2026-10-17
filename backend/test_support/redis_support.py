import re
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import redis
from testcontainers.core.container import DockerContainer

from kafka_support import free_port

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
STARTUP_TIMEOUT_SECONDS = 30
INTERNAL_PORT = 6379
PASSWORD = "test-redis-password"


def pinned_redis_image() -> str:
    compose = (REPOSITORY_ROOT / "docker-compose.yml").read_text()
    match = re.search(r"image:\s*(redis:\S+)", compose)
    assert match is not None, "docker-compose.yml no longer pins a Redis image"
    return match.group(1)


def cart_redis_flags() -> list[str]:
    compose = (REPOSITORY_ROOT / "docker-compose.yml").read_text()
    section = compose.split("  redis-cart:\n", 1)[1].split("  redis-cache:\n", 1)[0]
    command = re.search(r"exec redis-server(.*?)\n\s+environment:", section, re.DOTALL)
    assert command is not None, "could not read the redis-cart command from docker-compose.yml"
    flags = command.group(1).replace('--requirepass "$$REDIS_PASSWORD"', "").split()
    return [*flags]


def wait_until_ready(port: int) -> None:
    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        client = redis.Redis(port=port, password=PASSWORD, socket_connect_timeout=1)
        try:
            if client.ping():
                return
        except redis.RedisError:
            time.sleep(0.2)
        finally:
            client.close()
    raise TimeoutError("Redis did not become ready")


@dataclass(slots=True)
class RedisServer:
    port: int
    container: DockerContainer | None = None

    def start(self) -> None:
        container = (
            DockerContainer(pinned_redis_image())
            .with_bind_ports(INTERNAL_PORT, self.port)
            .with_command(["redis-server", "--requirepass", PASSWORD, *cart_redis_flags()])
        )
        container.start()
        self.container = container
        wait_until_ready(self.port)

    def restart(self) -> None:
        assert self.container is not None
        self.container.get_wrapped_container().restart(timeout=10)
        wait_until_ready(self.port)

    def stop(self) -> None:
        if self.container is not None:
            self.container.stop()
            self.container = None

    def config(self, name: str) -> str:
        client = redis.Redis(port=self.port, password=PASSWORD, decode_responses=True)
        try:
            return str(client.config_get(name)[name])
        finally:
            client.close()


@contextmanager
def run_redis() -> Iterator[RedisServer]:
    server = RedisServer(free_port())
    server.start()
    try:
        yield server
    finally:
        server.stop()
