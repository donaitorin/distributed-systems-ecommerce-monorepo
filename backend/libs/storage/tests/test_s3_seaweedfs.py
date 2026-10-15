import asyncio
import hashlib
from collections.abc import AsyncIterator, Iterator
from uuid import uuid4

import httpx
import pytest
from botocore.exceptions import ClientError

from ecommerce_storage import ObjectNotFoundError, S3ObjectStorage, build_s3_client
from seaweedfs_support import SeaweedFs

pytestmark = pytest.mark.integration

CACHE_CONTROL = "public, max-age=31536000, immutable"


@pytest.fixture
def storage(seaweedfs: SeaweedFs) -> S3ObjectStorage:
    return S3ObjectStorage(
        build_s3_client(seaweedfs.settings), seaweedfs.media_bucket, seaweedfs.public_base_url
    )


def unique_key() -> str:
    return f"tests/{uuid4().hex}.webp"


async def test_an_object_is_served_anonymously_with_its_headers(
    storage: S3ObjectStorage,
) -> None:
    key = unique_key()
    await storage.put(key, b"webp-bytes", "image/webp", cache_control=CACHE_CONTROL)

    async with httpx.AsyncClient() as http:
        response = await http.get(storage.public_url(key))
        head = await http.head(storage.public_url(key))

    assert response.content == b"webp-bytes"
    assert response.headers["Content-Type"] == "image/webp"
    assert response.headers["Cache-Control"] == CACHE_CONTROL
    assert head.status_code == 200
    assert head.headers["Cache-Control"] == CACHE_CONTROL


async def test_a_delete_removes_the_object_and_is_idempotent(storage: S3ObjectStorage) -> None:
    key = unique_key()
    await storage.put(key, b"x", "image/webp")

    await storage.delete(key)
    await storage.delete(key)

    async with httpx.AsyncClient() as http:
        assert (await http.get(storage.public_url(key))).status_code == 404


async def test_a_put_without_cache_control_stores_none(
    storage: S3ObjectStorage, seaweedfs: SeaweedFs
) -> None:
    key = unique_key()
    await storage.put(key, b"x", "image/webp")

    head = build_s3_client(seaweedfs.settings).head_object(Bucket="media", Key=key)

    assert "CacheControl" not in head


async def test_anonymous_clients_can_neither_write_delete_nor_list(
    storage: S3ObjectStorage, seaweedfs: SeaweedFs
) -> None:
    key = unique_key()
    await storage.put(key, b"x", "image/webp")
    url = storage.public_url(key)

    async with httpx.AsyncClient() as http:
        overwrite = await http.put(url, content=b"y")
        removal = await http.delete(url)
        listing = await http.get(f"{seaweedfs.endpoint}/{seaweedfs.media_bucket}?list-type=2")
        intact = await http.get(url)

    assert (overwrite.status_code, removal.status_code, listing.status_code) == (403, 403, 403)
    assert intact.content == b"x"


async def test_the_imports_bucket_is_private(seaweedfs: SeaweedFs) -> None:
    client = build_s3_client(seaweedfs.settings)
    key = unique_key()
    client.put_object(Bucket=seaweedfs.imports_bucket, Key=key, Body=b"secret")

    async with httpx.AsyncClient() as http:
        anonymous = await http.get(f"{seaweedfs.endpoint}/{seaweedfs.imports_bucket}/{key}")

    assert anonymous.status_code == 403
    client.delete_object(Bucket=seaweedfs.imports_bucket, Key=key)
    with pytest.raises(ClientError):
        client.head_object(Bucket=seaweedfs.imports_bucket, Key=key)


async def blocks(total: int, size: int, fail_after: int | None = None) -> AsyncIterator[bytes]:
    sent = 0
    index = 0
    while sent < total:
        if fail_after is not None and index == fail_after:
            raise RuntimeError("client went away")
        block = bytes([index % 251]) * min(size, total - sent)
        sent += len(block)
        index += 1
        yield block


def digest_of(chunks: Iterator[bytes]) -> tuple[str, int]:
    hasher = hashlib.sha256()
    total = 0
    for chunk in chunks:
        hasher.update(chunk)
        total += len(chunk)
    return hasher.hexdigest(), total


async def expected_digest(total: int, size: int) -> tuple[str, int]:
    hasher = hashlib.sha256()
    count = 0
    async for block in blocks(total, size):
        hasher.update(block)
        count += len(block)
    return hasher.hexdigest(), count


@pytest.fixture
def imports_storage(seaweedfs: SeaweedFs) -> S3ObjectStorage:
    return S3ObjectStorage(
        build_s3_client(seaweedfs.settings), seaweedfs.imports_bucket, seaweedfs.endpoint
    )


async def test_a_large_stream_is_uploaded_in_parts_and_read_back_identically(
    imports_storage: S3ObjectStorage,
) -> None:
    key = f"tests/{uuid4().hex}.csv"
    total = 21 * 1024 * 1024

    await imports_storage.put_stream(key, blocks(total, 1024 * 1024 + 7), "text/csv")

    read = await asyncio.to_thread(digest_of, imports_storage.read_chunks(key))
    assert read == await expected_digest(total, 1024 * 1024 + 7)


async def test_a_small_stream_is_uploaded_with_its_content_type(
    imports_storage: S3ObjectStorage, seaweedfs: SeaweedFs
) -> None:
    key = f"tests/{uuid4().hex}.csv"

    await imports_storage.put_stream(key, blocks(100, 10), "text/csv")

    head = build_s3_client(seaweedfs.settings).head_object(Bucket="imports", Key=key)
    assert head["ContentType"] == "text/csv"
    assert head["ContentLength"] == 100


async def test_a_stream_that_fails_midway_leaves_no_object(
    imports_storage: S3ObjectStorage, seaweedfs: SeaweedFs
) -> None:
    key = f"tests/{uuid4().hex}.csv"

    with pytest.raises(RuntimeError, match="client went away"):
        await imports_storage.put_stream(
            key, blocks(30 * 1024 * 1024, 1024 * 1024, fail_after=12), "text/csv"
        )

    with pytest.raises(ClientError):
        build_s3_client(seaweedfs.settings).head_object(Bucket="imports", Key=key)
    leftovers = build_s3_client(seaweedfs.settings).list_multipart_uploads(Bucket="imports")
    assert key not in [item["Key"] for item in leftovers.get("Uploads", [])]


async def test_reading_a_missing_object_is_not_found(imports_storage: S3ObjectStorage) -> None:
    with pytest.raises(ObjectNotFoundError):
        await asyncio.to_thread(list, imports_storage.read_chunks(f"tests/{uuid4().hex}.csv"))
