import logging

from ecommerce_resilience.breaker import CallOutcome, CircuitState

logger = logging.getLogger(__name__)


class LoggingListener:
    def state_changed(self, name: str, previous: CircuitState, current: CircuitState) -> None:
        logger.warning(
            "circuit breaker changed state",
            extra={"circuit": name, "from_state": previous.value, "to_state": current.value},
        )

    def call_finished(self, name: str, outcome: CallOutcome) -> None:
        return None
