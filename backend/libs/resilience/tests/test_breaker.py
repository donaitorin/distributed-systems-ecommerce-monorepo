import asyncio

import pytest

from ecommerce_resilience import (
    BreakerConfig,
    CallOutcome,
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
)


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class Recorder:
    def __init__(self) -> None:
        self.transitions: list[tuple[str, CircuitState, CircuitState]] = []
        self.outcomes: list[CallOutcome] = []

    def state_changed(self, name: str, previous: CircuitState, current: CircuitState) -> None:
        self.transitions.append((name, previous, current))

    def call_finished(self, name: str, outcome: CallOutcome) -> None:
        self.outcomes.append(outcome)


class Fixture:
    def __init__(self, config: BreakerConfig) -> None:
        self.clock = Clock()
        self.recorder = Recorder()
        self.breaker = CircuitBreaker("catalog", config, self.recorder, self.clock)

    def state(self) -> CircuitState:
        return self.breaker.state

    async def succeed(self) -> str:
        async def operation() -> str:
            return "ok"

        return await self.breaker.call(operation)

    async def fail(self) -> None:
        async def operation() -> None:
            raise ConnectionError("down")

        with pytest.raises(ConnectionError):
            await self.breaker.call(operation)

    async def trip(self, failures: int) -> None:
        for _ in range(failures):
            await self.fail()


@pytest.fixture
def fixture() -> Fixture:
    return Fixture(BreakerConfig(failure_threshold=3, open_seconds=10.0, half_open_probes=1))


async def test_a_new_breaker_is_closed_and_passes_calls_through(fixture: Fixture) -> None:
    assert fixture.state() is CircuitState.CLOSED
    assert await fixture.succeed() == "ok"
    assert fixture.recorder.outcomes == [CallOutcome.SUCCESS]


async def test_failures_below_the_threshold_keep_it_closed(fixture: Fixture) -> None:
    await fixture.trip(2)

    assert fixture.state() is CircuitState.CLOSED
    assert fixture.recorder.transitions == []


async def test_a_success_resets_the_count_of_consecutive_failures(fixture: Fixture) -> None:
    await fixture.trip(2)
    await fixture.succeed()
    await fixture.trip(2)

    assert fixture.state() is CircuitState.CLOSED


async def test_reaching_the_threshold_opens_the_circuit(fixture: Fixture) -> None:
    await fixture.trip(3)

    assert fixture.state() is CircuitState.OPEN
    assert fixture.recorder.transitions == [("catalog", CircuitState.CLOSED, CircuitState.OPEN)]


async def test_an_open_circuit_rejects_calls_without_running_them(fixture: Fixture) -> None:
    await fixture.trip(3)
    ran = False

    async def operation() -> None:
        nonlocal ran
        ran = True

    with pytest.raises(CircuitOpenError) as rejected:
        await fixture.breaker.call(operation)

    assert not ran
    assert rejected.value.name == "catalog"
    assert fixture.recorder.outcomes[-1] is CallOutcome.REJECTED


async def test_the_rejection_tells_how_long_to_wait(fixture: Fixture) -> None:
    await fixture.trip(3)
    fixture.clock.now += 3.5

    with pytest.raises(CircuitOpenError) as rejected:
        await fixture.succeed()

    assert rejected.value.retry_after_seconds == pytest.approx(6.5)
    assert rejected.value.retry_after_whole_seconds == 7


async def test_the_whole_retry_after_is_at_least_one_second() -> None:
    assert CircuitOpenError("x", 0.0).retry_after_whole_seconds == 1


async def test_it_stays_open_until_the_open_duration_has_passed(fixture: Fixture) -> None:
    await fixture.trip(3)
    fixture.clock.now += 9.99

    assert fixture.state() is CircuitState.OPEN


async def test_after_the_open_duration_it_becomes_half_open(fixture: Fixture) -> None:
    await fixture.trip(3)
    fixture.clock.now += 10.0

    assert fixture.state() is CircuitState.HALF_OPEN
    assert fixture.recorder.transitions[-1] == (
        "catalog",
        CircuitState.OPEN,
        CircuitState.HALF_OPEN,
    )


async def test_a_successful_probe_closes_the_circuit(fixture: Fixture) -> None:
    await fixture.trip(3)
    fixture.clock.now += 10.0

    assert await fixture.succeed() == "ok"

    assert fixture.state() is CircuitState.CLOSED
    assert fixture.recorder.transitions[-1][1:] == (CircuitState.HALF_OPEN, CircuitState.CLOSED)


async def test_after_closing_the_failure_count_starts_again(fixture: Fixture) -> None:
    await fixture.trip(3)
    fixture.clock.now += 10.0
    await fixture.succeed()

    await fixture.trip(2)

    assert fixture.state() is CircuitState.CLOSED


async def test_a_failed_probe_opens_the_circuit_again_for_a_full_duration(
    fixture: Fixture,
) -> None:
    await fixture.trip(3)
    fixture.clock.now += 10.0

    await fixture.fail()

    assert fixture.state() is CircuitState.OPEN
    assert fixture.breaker.retry_after_seconds() == pytest.approx(10.0)
    assert fixture.recorder.transitions[-1][1:] == (CircuitState.HALF_OPEN, CircuitState.OPEN)


async def test_half_open_lets_only_the_configured_number_of_probes_through() -> None:
    fixture = Fixture(BreakerConfig(failure_threshold=1, open_seconds=5.0, half_open_probes=2))
    await fixture.fail()
    fixture.clock.now += 5.0
    release = asyncio.Event()

    async def slow_probe() -> str:
        await release.wait()
        return "ok"

    first = asyncio.create_task(fixture.breaker.call(slow_probe))
    second = asyncio.create_task(fixture.breaker.call(slow_probe))
    await asyncio.sleep(0)

    with pytest.raises(CircuitOpenError):
        await fixture.breaker.call(slow_probe)
    release.set()
    assert list(await asyncio.gather(first, second)) == ["ok", "ok"]
    assert fixture.state() is CircuitState.CLOSED


async def test_every_probe_must_succeed_before_it_closes() -> None:
    fixture = Fixture(BreakerConfig(failure_threshold=1, open_seconds=5.0, half_open_probes=2))
    await fixture.fail()
    fixture.clock.now += 5.0

    await fixture.succeed()

    assert fixture.state() is CircuitState.HALF_OPEN
    await fixture.succeed()
    assert fixture.state() is CircuitState.CLOSED


async def test_an_error_that_is_not_a_failure_counts_as_a_healthy_answer(
    fixture: Fixture,
) -> None:
    async def not_found() -> None:
        raise KeyError("missing")

    for _ in range(5):
        with pytest.raises(KeyError):
            await fixture.breaker.call(not_found, is_failure=lambda error: False)

    assert fixture.state() is CircuitState.CLOSED
    assert fixture.recorder.outcomes == [CallOutcome.SUCCESS] * 5


async def test_a_cancelled_probe_frees_its_slot_without_counting_as_a_failure(
    fixture: Fixture,
) -> None:
    await fixture.trip(3)
    fixture.clock.now += 10.0
    started = asyncio.Event()

    async def hangs() -> None:
        started.set()
        await asyncio.sleep(60)

    probe = asyncio.create_task(fixture.breaker.call(hangs))
    await started.wait()
    probe.cancel()
    with pytest.raises(asyncio.CancelledError):
        await probe

    assert fixture.state() is CircuitState.HALF_OPEN
    assert await fixture.succeed() == "ok"
    assert fixture.state() is CircuitState.CLOSED


async def test_the_breaker_works_without_a_listener() -> None:
    breaker = CircuitBreaker("quiet", BreakerConfig(failure_threshold=1))

    async def boom() -> None:
        raise ConnectionError

    with pytest.raises(ConnectionError):
        await breaker.call(boom)

    assert breaker.state is CircuitState.OPEN


@pytest.mark.parametrize(
    "kwargs",
    [{"failure_threshold": 0}, {"open_seconds": 0}, {"half_open_probes": 0}],
)
def test_invalid_configuration_is_rejected(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValueError, match="must be"):
        BreakerConfig(**kwargs)  # type: ignore[arg-type]
