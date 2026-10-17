import asyncio
import inspect
from collections.abc import Awaitable, Callable

WAIT_SECONDS = 60.0
POLL_SECONDS = 0.05


async def eventually(
    condition: Callable[[], bool | Awaitable[bool]],
    seconds: float = WAIT_SECONDS,
    interval: float = POLL_SECONDS,
) -> None:
    async with asyncio.timeout(seconds):
        while True:
            outcome = condition()
            if await outcome if inspect.isawaitable(outcome) else outcome:
                return
            await asyncio.sleep(interval)
