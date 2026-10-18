import asyncio
import math
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CallOutcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    REJECTED = "rejected"


class BreakerListener(Protocol):
    def state_changed(self, name: str, previous: CircuitState, current: CircuitState) -> None: ...

    def call_finished(self, name: str, outcome: CallOutcome) -> None: ...


class SilentListener:
    def state_changed(self, name: str, previous: CircuitState, current: CircuitState) -> None:
        return None

    def call_finished(self, name: str, outcome: CallOutcome) -> None:
        return None


class CircuitOpenError(Exception):
    def __init__(self, name: str, retry_after_seconds: float) -> None:
        super().__init__(f"circuit {name} is open")
        self.name = name
        self.retry_after_seconds = retry_after_seconds

    @property
    def retry_after_whole_seconds(self) -> int:
        return max(1, math.ceil(self.retry_after_seconds))


@dataclass(frozen=True, slots=True)
class BreakerConfig:
    failure_threshold: int = 5
    open_seconds: float = 10.0
    half_open_probes: int = 1

    def __post_init__(self) -> None:
        if self.failure_threshold < 1:
            raise ValueError("failure_threshold must be at least 1")
        if self.open_seconds <= 0:
            raise ValueError("open_seconds must be positive")
        if self.half_open_probes < 1:
            raise ValueError("half_open_probes must be at least 1")


class CircuitBreaker:
    def __init__(
        self,
        name: str,
        config: BreakerConfig | None = None,
        listener: BreakerListener | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.name = name
        self._config = config or BreakerConfig()
        self._listener: BreakerListener = listener or SilentListener()
        self._clock = clock
        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._opened_at = 0.0
        self._probes_in_flight = 0
        self._probe_successes = 0

    @property
    def state(self) -> CircuitState:
        self._move_to_half_open_when_due()
        return self._state

    def retry_after_seconds(self) -> float:
        if self._state is not CircuitState.OPEN:
            return 0.0
        return max(0.0, self._opened_at + self._config.open_seconds - self._clock())

    async def call[ResultT](
        self,
        operation: Callable[[], Awaitable[ResultT]],
        is_failure: Callable[[BaseException], bool] = lambda error: True,
    ) -> ResultT:
        self._admit()
        try:
            result = await operation()
        except asyncio.CancelledError:
            self._release_probe()
            raise
        except Exception as error:
            if is_failure(error):
                self._record_failure()
            else:
                self._record_success()
            raise
        self._record_success()
        return result

    def _admit(self) -> None:
        self._move_to_half_open_when_due()
        if self._state is CircuitState.OPEN:
            self._reject()
        if self._state is CircuitState.HALF_OPEN:
            if self._probes_in_flight >= self._config.half_open_probes:
                self._reject()
            self._probes_in_flight += 1

    def _release_probe(self) -> None:
        if self._state is CircuitState.HALF_OPEN:
            self._probes_in_flight = max(0, self._probes_in_flight - 1)

    def _reject(self) -> None:
        self._listener.call_finished(self.name, CallOutcome.REJECTED)
        raise CircuitOpenError(self.name, self.retry_after_seconds())

    def _move_to_half_open_when_due(self) -> None:
        if self._state is CircuitState.OPEN and self.retry_after_seconds() == 0.0:
            self._probes_in_flight = 0
            self._probe_successes = 0
            self._transition(CircuitState.HALF_OPEN)

    def _record_success(self) -> None:
        self._listener.call_finished(self.name, CallOutcome.SUCCESS)
        if self._state is CircuitState.HALF_OPEN:
            self._probes_in_flight = max(0, self._probes_in_flight - 1)
            self._probe_successes += 1
            if self._probe_successes >= self._config.half_open_probes:
                self._consecutive_failures = 0
                self._transition(CircuitState.CLOSED)
        elif self._state is CircuitState.CLOSED:
            self._consecutive_failures = 0

    def _record_failure(self) -> None:
        self._listener.call_finished(self.name, CallOutcome.FAILURE)
        if self._state is CircuitState.HALF_OPEN:
            self._open()
        elif self._state is CircuitState.CLOSED:
            self._consecutive_failures += 1
            if self._consecutive_failures >= self._config.failure_threshold:
                self._open()

    def _open(self) -> None:
        self._opened_at = self._clock()
        self._probes_in_flight = 0
        self._probe_successes = 0
        self._transition(CircuitState.OPEN)

    def _transition(self, current: CircuitState) -> None:
        previous, self._state = self._state, current
        if previous is not current:
            self._listener.state_changed(self.name, previous, current)
