from collections.abc import Mapping
from dataclasses import dataclass
from typing import Self

DEFAULT_CLIENT_ID = "ecommerce"
DEFAULT_MAX_POLL_INTERVAL_MS = 1_800_000
DEFAULT_PUBLISH_TIMEOUT_SECONDS = 15.0


@dataclass(frozen=True, slots=True)
class KafkaSettings:
    bootstrap_servers: str
    client_id: str = DEFAULT_CLIENT_ID
    max_poll_interval_ms: int = DEFAULT_MAX_POLL_INTERVAL_MS
    publish_timeout_seconds: float = DEFAULT_PUBLISH_TIMEOUT_SECONDS

    @classmethod
    def from_env(cls, environ: Mapping[str, str], client_id: str = DEFAULT_CLIENT_ID) -> Self:
        return cls(
            bootstrap_servers=environ["KAFKA_BOOTSTRAP_SERVERS"],
            client_id=client_id,
            max_poll_interval_ms=int(
                environ.get("KAFKA_MAX_POLL_INTERVAL_MS", DEFAULT_MAX_POLL_INTERVAL_MS)
            ),
        )
