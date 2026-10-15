from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID, uuid4

from catalog.application.import_jobs import ImportJobs
from catalog.application.imports import ImportService
from catalog.application.ports import UnitOfWorkFactory
from catalog.domain.imports import ImportRecord, UploadResult
from catalog.infra.memory import InMemoryStore, InMemoryUnitOfWork
from catalog.infra.memory_imports import OutboxEntry
from catalog_testing.csv_import import CATEGORY_NAMES, SAMPLE_FILE
from catalog_testing.support import SteppingClock
from ecommerce_storage import InMemoryObjectStorage

SAMPLE = SAMPLE_FILE.read_bytes()


async def stream(data: bytes, size: int = 700) -> AsyncIterator[bytes]:
    for start in range(0, len(data), size):
        yield data[start : start + size]


def store_with_categories() -> InMemoryStore:
    store = InMemoryStore()
    store.seed_categories(*((name, name.lower().replace(" ", "-")) for name in CATEGORY_NAMES))
    return store


class ImportsHarness:
    def __init__(self, max_bytes: int = 50 * 1024 * 1024, batch_size: int = 1000) -> None:
        self.store = store_with_categories()
        self.storage = InMemoryObjectStorage()
        self.clock = SteppingClock()
        self.identifiers: list[UUID] = []
        self.unit_of_work: UnitOfWorkFactory = lambda: InMemoryUnitOfWork(self.store)
        self.service = ImportService(
            self.unit_of_work, self.storage, max_bytes, self.clock, self._new_id
        )
        self.jobs = ImportJobs(self.unit_of_work, self.storage, self.clock, batch_size)

    def _new_id(self) -> UUID:
        identifier = uuid4()
        self.identifiers.append(identifier)
        return identifier

    async def upload(
        self, data: bytes = SAMPLE, filename: str | None = "products.csv", user: str = "admin-1"
    ) -> UploadResult:
        return await self.service.upload(stream(data), user, uuid4(), lambda: filename)

    async def validated(self, data: bytes = SAMPLE) -> ImportRecord:
        result = await self.upload(data)
        await self.jobs.validate(result.record.id)
        return await self.service.get(result.record.id)

    @property
    def events(self) -> list[OutboxEntry]:
        return self.store.import_data.outbox

    def event_payloads(self, event_type: str) -> list[Any]:
        return [item.payload for item in self.events if item.event_type == event_type]
