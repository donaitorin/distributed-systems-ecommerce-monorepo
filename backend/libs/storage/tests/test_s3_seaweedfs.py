from uuid import uuid4

import httpx
import pytest
from botocore.exceptions import ClientError

from ecommerce_storage import S3ObjectStorage, build_s3_client
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
