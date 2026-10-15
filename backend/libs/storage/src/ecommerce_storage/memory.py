from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass

from ecommerce_storage.port import ObjectNotFoundError, validate_key
from ecommerce_storage.urls import build_public_url

READ_CHUNK_BYTES = 64 * 1024


@dataclass(frozen=True, slots=True)
class StoredObject:
    data: bytes
    content_type: str
    cache_control: str | None = None


class InMemoryObjectStorage:
    def __init__(self, public_base_url: str = "http://media.test") -> None:
        self._public_base_url = public_base_url
        self._objects: dict[str, StoredObject] = {}

    async def put(
        self, key: str, data: bytes, content_type: str, cache_control: str | None = None
    ) -> None:
        self._objects[validate_key(key)] = StoredObject(data, content_type, cache_control)

    async def put_stream(self, key: str, chunks: AsyncIterator[bytes], content_type: str) -> None:
        validated = validate_key(key)
        collected = bytearray()
        async for chunk in chunks:
            collected += chunk
        self._objects[validated] = StoredObject(bytes(collected), content_type)

    def read_chunks(self, key: str) -> Iterator[bytes]:
        stored = self._objects.get(validate_key(key))
        if stored is None:
            raise ObjectNotFoundError(f"no object with key {key}")
        for start in range(0, len(stored.data), READ_CHUNK_BYTES):
            yield stored.data[start : start + READ_CHUNK_BYTES]

    async def delete(self, key: str) -> None:
        self._objects.pop(validate_key(key), None)

    def public_url(self, key: str) -> str:
        return build_public_url(self._public_base_url, key)

    def get(self, key: str) -> StoredObject | None:
        return self._objects.get(key)

    def keys(self) -> list[str]:
        return sorted(self._objects)
