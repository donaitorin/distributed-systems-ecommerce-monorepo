import pytest

from ecommerce_storage import InMemoryObjectStorage, InvalidObjectKeyError, ObjectStorage


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
