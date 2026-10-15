import asyncio
from dataclasses import dataclass

from argon2 import PasswordHasher as Argon2
from argon2.exceptions import InvalidHashError, VerificationError

DEFAULT_MEMORY_COST_KIB = 19456
DEFAULT_TIME_COST = 2
DEFAULT_PARALLELISM = 1
DEFAULT_CONCURRENCY = 4
DECOY_PASSWORD = "decoy-password-for-unknown-emails"


@dataclass(frozen=True, slots=True)
class HashingSettings:
    memory_cost_kib: int = DEFAULT_MEMORY_COST_KIB
    time_cost: int = DEFAULT_TIME_COST
    parallelism: int = DEFAULT_PARALLELISM
    concurrency: int = DEFAULT_CONCURRENCY


class Argon2idHasher:
    def __init__(self, settings: HashingSettings | None = None) -> None:
        resolved = settings or HashingSettings()
        self._argon2 = Argon2(
            time_cost=resolved.time_cost,
            memory_cost=resolved.memory_cost_kib,
            parallelism=resolved.parallelism,
        )
        self._slots = asyncio.Semaphore(resolved.concurrency)
        self._decoy_hash = self._argon2.hash(DECOY_PASSWORD)

    async def hash(self, password: str) -> str:
        async with self._slots:
            return await asyncio.to_thread(self._argon2.hash, password)

    async def verify(self, password_hash: str, password: str) -> bool:
        async with self._slots:
            return await asyncio.to_thread(self._verify, password_hash, password)

    async def verify_decoy(self, password: str) -> None:
        await self.verify(self._decoy_hash, password)

    def needs_rehash(self, password_hash: str) -> bool:
        return self._argon2.check_needs_rehash(password_hash)

    def _verify(self, password_hash: str, password: str) -> bool:
        try:
            return self._argon2.verify(password_hash, password)
        except (VerificationError, InvalidHashError):
            return False
