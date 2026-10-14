from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ServiceSettings:
    name: str
    version: str = "0.1.0"
    log_level: str = "INFO"
    readiness_timeout_seconds: float = 2.0
