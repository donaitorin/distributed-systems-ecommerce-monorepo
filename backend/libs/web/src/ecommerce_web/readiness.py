import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

logger = logging.getLogger(__name__)

STATUS_OK = "ok"
STATUS_FAILED = "failed"
STATUS_TIMEOUT = "timeout"


@dataclass(frozen=True, slots=True)
class ReadinessCheck:
    name: str
    probe: Callable[[], Awaitable[None]]


async def _run_check(check: ReadinessCheck, timeout_seconds: float) -> tuple[str, str]:
    try:
        async with asyncio.timeout(timeout_seconds):
            await check.probe()
    except TimeoutError:
        logger.warning("readiness check timed out", extra={"check": check.name})
        return check.name, STATUS_TIMEOUT
    except Exception:
        logger.warning("readiness check failed", extra={"check": check.name}, exc_info=True)
        return check.name, STATUS_FAILED
    return check.name, STATUS_OK


async def run_readiness_checks(
    checks: Sequence[ReadinessCheck], timeout_seconds: float
) -> dict[str, str]:
    results = await asyncio.gather(*(_run_check(check, timeout_seconds) for check in checks))
    return dict(results)
