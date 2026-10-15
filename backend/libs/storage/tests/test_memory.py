from collections.abc import AsyncIterator

import pytest

from ecommerce_storage import (
    InMemoryObjectStorage,
    InvalidObjectKeyError,
    ObjectNotFoundError,
    ObjectStorage,
)


def test_in_memory_adapter_satisfies_the_port() -> None:
    storage: ObjectStorage = InMemoryObjectStorage()

    assert storage.public_url("products/a.webp")


async def test_put_stores_the_bytes_and_content_type() -> None:
    storage = InMemoryObjectStorage()

    await storage.put("products/a.webp", b"image", "image/webp")

    stored = storage.get("products/a.webp")
    assert stored is not None
    assert (stored.data, stored.content_type) == (b"image", "image/webp")


async def test_put_overwrites_an_existing_key() -> None:
    storage = InMemoryObjectStorage()
    await storage.put("a", b"one", "text/plain")

    await storage.put("a", b"two", "text/plain")

    stored = storage.get("a")
    assert storage.keys() == ["a"]
    assert stored is not None
    assert stored.data == b"two"


async def test_delete_removes_the_object_and_is_idempotent() -> None:
    storage = InMemoryObjectStorage()
    await storage.put("a", b"x", "text/plain")

    await storage.delete("a")
    await storage.delete("a")

    assert storage.get("a") is None
    assert storage.keys() == []


def test_public_url_joins_base_url_and_key() -> None:
    storage = InMemoryObjectStorage("https://cdn.example.com/media/")

    assert storage.public_url("products/sku-1/img.webp") == (
        "https://cdn.example.com/media/products/sku-1/img.webp"
    )


def test_public_url_escapes_unsafe_characters() -> None:
    storage = InMemoryObjectStorage("https://cdn.example.com")

    assert storage.public_url("products/a b/é.webp") == (
        "https://cdn.example.com/products/a%20b/%C3%A9.webp"
    )


@pytest.mark.parametrize("key", ["", "/abs", "a//b", "../escape", "a/../b", "a/./b", "trailing/"])
async def test_invalid_keys_are_rejected(key: str) -> None:
    storage = InMemoryObjectStorage()

    with pytest.raises(InvalidObjectKeyError):
        await storage.put(key, b"x", "text/plain")
    with pytest.raises(InvalidObjectKeyError):
        await storage.delete(key)
    with pytest.raises(InvalidObjectKeyError):
        storage.public_url(key)


async def test_put_keeps_the_cache_control_when_given() -> None:
    storage = InMemoryObjectStorage()

    await storage.put("a", b"x", "image/webp", cache_control="public, max-age=60")
    await storage.put("b", b"x", "image/webp")

    first, second = storage.get("a"), storage.get("b")
    assert first is not None
    assert second is not None
    assert first.cache_control == "public, max-age=60"
    assert second.cache_control is None


async def chunks_of(*parts: bytes) -> AsyncIterator[bytes]:
    for part in parts:
        yield part


async def test_put_stream_stores_the_concatenated_chunks() -> None:
    storage = InMemoryObjectStorage()

    await storage.put_stream("imports/a.csv", chunks_of(b"one,", b"two\n", b"three"), "text/csv")

    stored = storage.get("imports/a.csv")
    assert stored is not None
    assert (stored.data, stored.content_type) == (b"one,two\nthree", "text/csv")


async def test_a_stream_that_fails_stores_nothing() -> None:
    storage = InMemoryObjectStorage()

    async def failing() -> AsyncIterator[bytes]:
        yield b"partial"
        raise RuntimeError("upload aborted")

    with pytest.raises(RuntimeError):
        await storage.put_stream("imports/a.csv", failing(), "text/csv")

    assert storage.keys() == []


async def test_read_chunks_returns_the_object_in_slices() -> None:
    storage = InMemoryObjectStorage()
    data = b"x" * (64 * 1024 * 2 + 10)
    await storage.put("imports/a.csv", data, "text/csv")

    chunks = list(storage.read_chunks("imports/a.csv"))

    assert [len(chunk) for chunk in chunks] == [65536, 65536, 10]
    assert b"".join(chunks) == data


def test_reading_a_missing_object_is_reported() -> None:
    with pytest.raises(ObjectNotFoundError):
        list(InMemoryObjectStorage().read_chunks("imports/missing.csv"))


async def test_streaming_keys_are_validated() -> None:
    with pytest.raises(InvalidObjectKeyError):
        await InMemoryObjectStorage().put_stream("../escape", chunks_of(b"x"), "text/csv")
    with pytest.raises(InvalidObjectKeyError):
        list(InMemoryObjectStorage().read_chunks(""))
