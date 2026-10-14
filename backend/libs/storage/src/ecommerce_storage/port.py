from typing import Protocol


class InvalidObjectKeyError(ValueError):
    pass


class ObjectStorage(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> None: ...

    async def delete(self, key: str) -> None: ...

    def public_url(self, key: str) -> str: ...


def validate_key(key: str) -> str:
    segments = key.split("/")
    if not key or key.startswith("/") or any(segment in {"", ".", ".."} for segment in segments):
        raise InvalidObjectKeyError(f"invalid object key: {key!r}")
    return key
