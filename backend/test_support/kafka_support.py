import asyncio
import re
import socket
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from aiokafka.admin import AIOKafkaAdminClient
from testcontainers.core.container import DockerContainer

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
STARTUP_TIMEOUT_SECONDS = 90
INTERNAL_PORT = 9092


def pinned_kafka_image() -> str:
    compose = (REPOSITORY_ROOT / "docker-compose.yml").read_text()
    match = re.search(r"image:\s*(apache/kafka:\S+)", compose)
    assert match is not None, "docker-compose.yml no longer pins a Kafka image"
    return match.group(1)


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


async def broker_answers(bootstrap: str) -> bool:
    admin = AIOKafkaAdminClient(bootstrap_servers=bootstrap, request_timeout_ms=3000)
    try:
        await admin.start()
        await admin.list_topics()
    except Exception:
        return False
    finally:
        try:
            await admin.close()
        except Exception:
            return False
    return True


def probe(bootstrap: str) -> bool:
    return asyncio.run(broker_answers(bootstrap))


def wait_until_ready(bootstrap: str) -> None:
    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    with ThreadPoolExecutor(max_workers=1) as pool:
        while time.monotonic() < deadline:
            if pool.submit(probe, bootstrap).result():
                return
            time.sleep(1)
    raise TimeoutError("Kafka did not become ready")


@dataclass(slots=True)
class KafkaBroker:
    port: int
    container: DockerContainer | None = None

    @property
    def bootstrap(self) -> str:
        return f"127.0.0.1:{self.port}"

    def start(self) -> None:
        container = (
            DockerContainer(pinned_kafka_image())
            .with_bind_ports(INTERNAL_PORT, self.port)
            .with_env("KAFKA_NODE_ID", "1")
            .with_env("KAFKA_PROCESS_ROLES", "broker,controller")
            .with_env("KAFKA_CONTROLLER_QUORUM_VOTERS", "1@localhost:9093")
            .with_env("KAFKA_LISTENERS", "PLAINTEXT://:9092,CONTROLLER://:9093")
            .with_env("KAFKA_ADVERTISED_LISTENERS", f"PLAINTEXT://127.0.0.1:{self.port}")
            .with_env(
                "KAFKA_LISTENER_SECURITY_PROTOCOL_MAP", "CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT"
            )
            .with_env("KAFKA_INTER_BROKER_LISTENER_NAME", "PLAINTEXT")
            .with_env("KAFKA_CONTROLLER_LISTENER_NAMES", "CONTROLLER")
            .with_env("KAFKA_AUTO_CREATE_TOPICS_ENABLE", "true")
            .with_env("KAFKA_NUM_PARTITIONS", "3")
            .with_env("KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR", "1")
            .with_env("KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR", "1")
            .with_env("KAFKA_TRANSACTION_STATE_LOG_MIN_ISR", "1")
            .with_env("KAFKA_GROUP_INITIAL_REBALANCE_DELAY_MS", "0")
        )
        container.start()
        self.container = container
        wait_until_ready(self.bootstrap)

    def pause(self) -> None:
        assert self.container is not None
        self.container.get_wrapped_container().stop(timeout=5)

    def resume(self) -> None:
        assert self.container is not None
        self.container.get_wrapped_container().start()
        wait_until_ready(self.bootstrap)

    def stop(self) -> None:
        if self.container is not None:
            self.container.stop()
            self.container = None


@contextmanager
def run_kafka() -> Iterator[KafkaBroker]:
    broker = KafkaBroker(free_port())
    broker.start()
    try:
        yield broker
    finally:
        broker.stop()
