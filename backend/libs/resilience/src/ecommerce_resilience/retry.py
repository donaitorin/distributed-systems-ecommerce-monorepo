import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

type Sleeper = Callable[[float], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class ReadRetryPolicy:
    attempts: int = 2
    initial_delay_seconds: float = 0.1
    max_delay_seconds: float = 0.5

    def __post_init__(self) -> None:
        if self.attempts < 1:
            raise ValueError("attempts must be at least 1")
        if self.initial_delay_seconds < 0 or self.max_delay_seconds < self.initial_delay_seconds:
            raise ValueError("delays must satisfy 0 <= initial <= max")


async def retry_idempotent_read[ResultT](
    operation: Callable[[], Awaitable[ResultT]],
    policy: ReadRetryPolicy,
    is_retryable: Callable[[BaseException], bool],
    sleep: Sleeper = asyncio.sleep,
) -> ResultT:
    retrying = AsyncRetrying(
        stop=stop_after_attempt(policy.attempts),
        wait=wait_exponential_jitter(
            multiplier=policy.initial_delay_seconds,
            max=policy.max_delay_seconds,
            jitter=policy.initial_delay_seconds,
        ),
        retry=retry_if_exception(is_retryable),
        sleep=sleep,
        reraise=True,
    )

    async def attempt() -> ResultT:
        return await operation()

    return await retrying(attempt)
