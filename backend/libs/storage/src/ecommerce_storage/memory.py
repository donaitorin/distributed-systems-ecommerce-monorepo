from dataclasses import dataclass

from ecommerce_storage.port import validate_key
from ecommerce_storage.urls import build_public_url


@dataclass(frozen=True, slots=True)
class StoredObject:
    data: bytes
    content_type: str


class InMemoryObjectStorage:
    def __init__(self, public_base_url: str = "http://media.test") -> None:
        self._public_base_url = public_base_url
        self._objects: dict[str, StoredObject] = {}

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        self._objects[validate_key(key)] = StoredObject(data=data, content_type=content_type)

    async def delete(self, key: str) -> None:
        self._objects.pop(validate_key(key), None)

    def public_url(self, key: str) -> str:
        return build_public_url(self._public_base_url, key)

    def get(self, key: str) -> StoredObject | None:
        return self._objects.get(key)

    def keys(self) -> list[str]:
        return sorted(self._objects)
