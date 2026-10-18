import pytest

from ecommerce_resilience import ReadRetryPolicy, retry_idempotent_read


class Sleeps:
    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)


def transient(error: BaseException) -> bool:
    return isinstance(error, ConnectionError)


class Flaky:
    def __init__(self, failures: int, error: Exception | None = None) -> None:
        self.failures = failures
        self.error = error or ConnectionError("reset")
        self.calls = 0

    async def __call__(self) -> str:
        self.calls += 1
        if self.calls <= self.failures:
            raise self.error
        return "ok"


async def test_a_call_that_works_runs_once() -> None:
    operation, sleeps = Flaky(0), Sleeps()

    assert await retry_idempotent_read(operation, ReadRetryPolicy(), transient, sleeps) == "ok"
    assert (operation.calls, sleeps.delays) == (1, [])


async def test_a_transient_failure_is_retried_after_a_short_pause() -> None:
    operation, sleeps = Flaky(1), Sleeps()
    policy = ReadRetryPolicy(attempts=3, initial_delay_seconds=0.1, max_delay_seconds=0.5)

    assert await retry_idempotent_read(operation, policy, transient, sleeps) == "ok"

    assert operation.calls == 2
    assert len(sleeps.delays) == 1
    assert 0.1 <= sleeps.delays[0] <= 0.2


async def test_the_last_error_is_raised_when_every_attempt_fails() -> None:
    operation, sleeps = Flaky(10), Sleeps()
    policy = ReadRetryPolicy(attempts=3, initial_delay_seconds=0.1, max_delay_seconds=0.5)

    with pytest.raises(ConnectionError):
        await retry_idempotent_read(operation, policy, transient, sleeps)

    assert operation.calls == 3
    assert len(sleeps.delays) == 2


async def test_the_pauses_grow_but_never_pass_the_maximum() -> None:
    operation, sleeps = Flaky(10), Sleeps()
    policy = ReadRetryPolicy(attempts=6, initial_delay_seconds=0.1, max_delay_seconds=0.3)

    with pytest.raises(ConnectionError):
        await retry_idempotent_read(operation, policy, transient, sleeps)

    assert sleeps.delays[0] < sleeps.delays[-1] or sleeps.delays[-1] == 0.3
    assert max(sleeps.delays) <= 0.3


async def test_the_pauses_are_jittered() -> None:
    seen: set[float] = set()
    policy = ReadRetryPolicy(attempts=2, initial_delay_seconds=0.1, max_delay_seconds=1.0)
    for _ in range(20):
        sleeps = Sleeps()
        await retry_idempotent_read(Flaky(1), policy, transient, sleeps)
        seen.add(sleeps.delays[0])

    assert len(seen) > 1


async def test_an_error_that_is_not_transient_is_not_retried() -> None:
    operation, sleeps = Flaky(5, ValueError("bad")), Sleeps()

    with pytest.raises(ValueError, match="bad"):
        await retry_idempotent_read(operation, ReadRetryPolicy(attempts=3), transient, sleeps)

    assert (operation.calls, sleeps.delays) == (1, [])


async def test_one_attempt_means_no_retry() -> None:
    operation = Flaky(1)

    with pytest.raises(ConnectionError):
        await retry_idempotent_read(operation, ReadRetryPolicy(attempts=1), transient, Sleeps())

    assert operation.calls == 1


@pytest.mark.parametrize(
    "kwargs",
    [
        {"attempts": 0},
        {"initial_delay_seconds": -1.0},
        {"initial_delay_seconds": 2.0, "max_delay_seconds": 1.0},
    ],
)
def test_an_invalid_policy_is_rejected(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValueError, match="must"):
        ReadRetryPolicy(**kwargs)  # type: ignore[arg-type]


async def test_a_plain_function_returning_a_coroutine_is_awaited() -> None:
    async def read() -> str:
        return "value"

    assert (
        await retry_idempotent_read(lambda: read(), ReadRetryPolicy(), transient, Sleeps())
        == "value"
    )
