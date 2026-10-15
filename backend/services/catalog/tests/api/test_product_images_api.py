from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from catalog_testing import images
from catalog_testing.support import (
    MEDIA_BASE_URL,
    SteppingClock,
    build_test_app,
    http_client,
    valid_product,
)
from fastapi import FastAPI

from catalog.domain.image import MAX_UPLOAD_BYTES
from catalog.infra.memory import InMemoryStore, InMemoryUnitOfWork
from ecommerce_auth.testing import StubTokenIssuer
from ecommerce_storage import InMemoryObjectStorage, ObjectStorageError

IMAGE_URL = "/api/v1/products/RS-001/image"


async def create_product(client: httpx.AsyncClient, admin: dict[str, str]) -> None:
    response = await client.post("/api/v1/products", json=valid_product(), headers=admin)
    assert response.status_code == 201


def upload(
    data: bytes,
    filename: str = "photo.jpg",
    content_type: str = "image/jpeg",
    field: str = "file",
) -> dict[str, Any]:
    body, header = images.multipart([(field, filename, data, content_type)])
    return {"content": body, "headers": {"Content-Type": header}}


async def put_image(
    client: httpx.AsyncClient,
    admin: dict[str, str],
    data: bytes,
    if_match: str = "*",
    **options: str,
) -> httpx.Response:
    request = upload(data, **options)
    return await client.put(
        IMAGE_URL,
        content=request["content"],
        headers=admin | request["headers"] | {"If-Match": if_match},
    )


@pytest.fixture
async def product(client: httpx.AsyncClient, admin: dict[str, str]) -> None:
    await create_product(client, admin)


async def test_uploading_an_image_returns_the_product_with_both_urls_and_a_new_etag(
    client: httpx.AsyncClient,
    admin: dict[str, str],
    storage: InMemoryObjectStorage,
    product: None,
) -> None:
    response = await put_image(client, admin, images.jpeg((2400, 1600)))

    body = response.json()
    assert response.status_code == 200
    assert response.headers["ETag"] == '"2"'
    assert body["version"] == 2
    assert body["image_url"].startswith(f"{MEDIA_BASE_URL}/products/RS-001/")
    assert body["image_url"].endswith("-1200.webp")
    assert body["thumbnail_url"].endswith("-400.webp")
    assert body["image_url"].removesuffix("-1200.webp") == body["thumbnail_url"].removesuffix(
        "-400.webp"
    )
    assert len(storage.keys()) == 2
    stored = [storage.get(key) for key in storage.keys()]  # noqa: SIM118
    assert [item.content_type for item in stored if item is not None] == ["image/webp"] * 2


async def test_the_urls_appear_on_get_and_in_listings(
    client: httpx.AsyncClient, admin: dict[str, str], product: None
) -> None:
    uploaded = (await put_image(client, admin, images.png())).json()

    fetched = (await client.get("/api/v1/products/RS-001")).json()
    listed = (await client.get("/api/v1/products")).json()["items"][0]

    assert fetched["image_url"] == uploaded["image_url"]
    assert listed["thumbnail_url"] == uploaded["thumbnail_url"]
    assert fetched["version"] == 2


@pytest.mark.parametrize(
    ("data", "filename", "content_type"),
    [
        (images.jpeg(), "photo.txt", "text/plain"),
        (images.png(), "photo.jpg", "image/jpeg"),
        (images.webp(), "noextension", "application/octet-stream"),
    ],
)
async def test_validation_looks_at_the_content_not_at_the_name_or_content_type(
    client: httpx.AsyncClient,
    admin: dict[str, str],
    product: None,
    data: bytes,
    filename: str,
    content_type: str,
) -> None:
    response = await put_image(client, admin, data, filename=filename, content_type=content_type)

    assert response.status_code == 200


@pytest.mark.parametrize(
    "data",
    [b"just some text pretending to be a jpeg" * 4, b"GIF89a" + b"0" * 40, b"%PDF-1.7" + b"0" * 40],
)
async def test_a_file_that_is_not_a_supported_image_is_a_415_even_if_named_jpg(
    client: httpx.AsyncClient,
    admin: dict[str, str],
    storage: InMemoryObjectStorage,
    product: None,
    data: bytes,
) -> None:
    response = await put_image(client, admin, data, filename="photo.jpg", content_type="image/jpeg")

    assert response.status_code == 415
    assert response.headers["content-type"].startswith("application/problem+json")
    assert storage.keys() == []


async def test_a_very_short_text_file_is_also_a_415(
    client: httpx.AsyncClient, admin: dict[str, str], product: None
) -> None:
    response = await put_image(client, admin, b"hi", filename="photo.jpg")

    assert response.status_code == 415


async def test_an_oversized_upload_is_a_413_and_is_not_read_to_the_end(
    client: httpx.AsyncClient, admin: dict[str, str], storage: InMemoryObjectStorage, product: None
) -> None:
    sent = 0
    chunk = b"\xff\xd8\xff\xe0" + b"0" * (1024 * 1024 - 4)

    async def endless_body() -> AsyncIterator[bytes]:
        nonlocal sent
        yield b'--b\r\nContent-Disposition: form-data; name="file"; filename="a.jpg"\r\n\r\n'
        for _ in range(100):
            sent += 1
            yield chunk
        yield b"\r\n--b--\r\n"

    response = await client.put(
        IMAGE_URL,
        content=endless_body(),
        headers=admin | {"Content-Type": "multipart/form-data; boundary=b", "If-Match": "*"},
    )

    assert response.status_code == 413
    assert response.json()["title"] == "Image too large"
    assert sent <= 7
    assert storage.keys() == []


async def test_a_declared_length_over_the_limit_is_refused_without_reading_the_body(
    client: httpx.AsyncClient, admin: dict[str, str], product: None
) -> None:
    request = upload(images.jpeg())

    response = await client.put(
        IMAGE_URL,
        content=request["content"],
        headers=admin
        | request["headers"]
        | {"If-Match": "*", "Content-Length": str(MAX_UPLOAD_BYTES * 3)},
    )

    assert response.status_code == 413


async def test_a_file_exactly_at_the_limit_is_not_a_413(
    client: httpx.AsyncClient, admin: dict[str, str], product: None
) -> None:
    padded = images.jpeg((64, 64)) + b"\x00" * MAX_UPLOAD_BYTES
    data = padded[:MAX_UPLOAD_BYTES]

    response = await put_image(client, admin, data)

    assert response.status_code != 413


async def test_a_file_one_byte_over_the_limit_is_a_413(
    client: httpx.AsyncClient, admin: dict[str, str], product: None
) -> None:
    data = (images.jpeg((64, 64)) + b"\x00" * MAX_UPLOAD_BYTES)[: MAX_UPLOAD_BYTES + 1]

    response = await put_image(client, admin, data)

    assert response.status_code == 413


async def test_a_corrupt_image_with_a_valid_signature_is_a_422(
    client: httpx.AsyncClient, admin: dict[str, str], storage: InMemoryObjectStorage, product: None
) -> None:
    response = await put_image(client, admin, images.jpeg()[:300])

    assert response.status_code == 422
    error = response.json()["errors"][0]
    assert (error["location"], error["type"]) == ("body.file", "invalid_image")
    assert storage.keys() == []


async def test_a_decompression_bomb_is_a_422(
    client: httpx.AsyncClient, admin: dict[str, str], product: None
) -> None:
    response = await put_image(client, admin, images.png_declaring(30_000, 30_000))

    assert response.status_code == 422
    assert response.json()["errors"][0]["type"] == "image_too_large"


async def test_a_missing_file_part_is_a_422(
    client: httpx.AsyncClient, admin: dict[str, str], product: None
) -> None:
    request = upload(images.jpeg(), field="photo")

    response = await client.put(
        IMAGE_URL,
        content=request["content"],
        headers=admin | request["headers"] | {"If-Match": "*"},
    )

    assert response.status_code == 422
    assert response.json()["errors"][0]["type"] == "missing_file"


async def test_two_file_parts_are_a_422(
    client: httpx.AsyncClient, admin: dict[str, str], product: None
) -> None:
    body, header = images.multipart(
        [
            ("file", "a.jpg", images.jpeg(), "image/jpeg"),
            ("file", "b.jpg", images.jpeg(), "image/jpeg"),
        ]
    )

    response = await client.put(
        IMAGE_URL, content=body, headers=admin | {"Content-Type": header, "If-Match": "*"}
    )

    assert response.status_code == 422
    assert response.json()["errors"][0]["type"] == "multiple_files"


async def test_other_form_fields_are_ignored(
    client: httpx.AsyncClient, admin: dict[str, str], product: None
) -> None:
    body, header = images.multipart(
        [("note", "n.txt", b"hello", "text/plain"), ("file", "a.jpg", images.jpeg(), "image/jpeg")]
    )

    response = await client.put(
        IMAGE_URL, content=body, headers=admin | {"Content-Type": header, "If-Match": "*"}
    )

    assert response.status_code == 200


@pytest.mark.parametrize("content_type", ["application/json", "image/jpeg", "text/plain"])
async def test_a_body_that_is_not_multipart_is_a_415(
    client: httpx.AsyncClient, admin: dict[str, str], product: None, content_type: str
) -> None:
    response = await client.put(
        IMAGE_URL,
        content=images.jpeg(),
        headers=admin | {"Content-Type": content_type, "If-Match": "*"},
    )

    assert response.status_code == 415


async def test_a_request_without_a_content_type_is_a_415(
    client: httpx.AsyncClient, admin: dict[str, str], product: None
) -> None:
    response = await client.put(IMAGE_URL, content=images.jpeg(), headers=admin | {"If-Match": "*"})

    assert response.status_code == 415


async def test_a_garbled_multipart_body_is_a_422(
    client: httpx.AsyncClient, admin: dict[str, str], product: None
) -> None:
    response = await client.put(
        IMAGE_URL,
        content=b"--wrong\r\nthis is not a multipart document",
        headers=admin | {"Content-Type": "multipart/form-data; boundary=right", "If-Match": "*"},
    )

    assert response.status_code == 422


@pytest.mark.parametrize("method", ["PUT", "DELETE"])
async def test_images_are_admin_only(
    client: httpx.AsyncClient,
    customer: dict[str, str],
    storage: InMemoryObjectStorage,
    product: None,
    method: str,
) -> None:
    request = upload(images.jpeg())

    anonymous = await client.request(
        method,
        IMAGE_URL,
        content=request["content"],
        headers=request["headers"] | {"If-Match": "*"},
    )
    forbidden = await client.request(
        method,
        IMAGE_URL,
        content=request["content"],
        headers=customer | request["headers"] | {"If-Match": "*"},
    )

    assert anonymous.status_code == 401
    assert forbidden.status_code == 403
    assert storage.keys() == []


@pytest.mark.parametrize("method", ["PUT", "DELETE"])
async def test_if_match_is_required(
    client: httpx.AsyncClient, admin: dict[str, str], product: None, method: str
) -> None:
    request = upload(images.jpeg())

    response = await client.request(
        method, IMAGE_URL, content=request["content"], headers=admin | request["headers"]
    )

    assert response.status_code == 428


async def test_a_stale_version_is_a_412_and_stores_nothing(
    client: httpx.AsyncClient, admin: dict[str, str], storage: InMemoryObjectStorage, product: None
) -> None:
    response = await put_image(client, admin, images.jpeg(), if_match='"9"')

    assert response.status_code == 412
    assert storage.keys() == []


async def test_an_unknown_sku_is_a_404_before_the_body_is_read(
    client: httpx.AsyncClient, admin: dict[str, str]
) -> None:
    response = await client.put(
        "/api/v1/products/NOPE-1/image",
        content=b"not even multipart",
        headers=admin | {"If-Match": "*"},
    )

    assert response.status_code == 404


async def test_replacing_the_image_changes_the_url_and_deletes_the_old_objects(
    client: httpx.AsyncClient,
    admin: dict[str, str],
    storage: InMemoryObjectStorage,
    product: None,
) -> None:
    first = (await put_image(client, admin, images.jpeg())).json()
    old_keys = set(storage.keys())

    second = await put_image(client, admin, images.png(), if_match='"2"')

    body = second.json()
    assert second.status_code == 200
    assert body["image_url"] != first["image_url"]
    assert body["version"] == 3
    assert set(storage.keys()).isdisjoint(old_keys)
    assert len(storage.keys()) == 2


async def test_deleting_the_image_clears_the_urls_and_removes_the_objects(
    client: httpx.AsyncClient,
    admin: dict[str, str],
    storage: InMemoryObjectStorage,
    product: None,
) -> None:
    await put_image(client, admin, images.jpeg())

    response = await client.delete(IMAGE_URL, headers=admin | {"If-Match": '"2"'})

    body = response.json()
    assert response.status_code == 200
    assert response.headers["ETag"] == '"3"'
    assert (body["image_url"], body["thumbnail_url"], body["version"]) == (None, None, 3)
    assert storage.keys() == []


async def test_deleting_a_missing_image_is_a_404(
    client: httpx.AsyncClient, admin: dict[str, str], product: None
) -> None:
    response = await client.delete(IMAGE_URL, headers=admin | {"If-Match": "*"})

    assert response.status_code == 404
    assert (await client.get("/api/v1/products/RS-001")).json()["version"] == 1


async def test_deleting_with_a_stale_version_is_a_412(
    client: httpx.AsyncClient, admin: dict[str, str], product: None
) -> None:
    await put_image(client, admin, images.jpeg())

    response = await client.delete(IMAGE_URL, headers=admin | {"If-Match": '"1"'})

    assert response.status_code == 412


async def test_deleting_the_product_does_not_remove_its_images(
    client: httpx.AsyncClient, admin: dict[str, str], storage: InMemoryObjectStorage, product: None
) -> None:
    await put_image(client, admin, images.jpeg())

    await client.delete("/api/v1/products/RS-001", headers=admin | {"If-Match": "*"})

    assert len(storage.keys()) == 2


class UnavailableStorage(InMemoryObjectStorage):
    def __init__(self) -> None:
        super().__init__(MEDIA_BASE_URL)
        self.down = False

    async def put(
        self, key: str, data: bytes, content_type: str, cache_control: str | None = None
    ) -> None:
        if self.down:
            raise ObjectStorageError("connection refused")
        await super().put(key, data, content_type, cache_control)

    async def delete(self, key: str) -> None:
        if self.down:
            raise ObjectStorageError("connection refused")
        await super().delete(key)


@pytest.fixture
async def flaky() -> UnavailableStorage:
    return UnavailableStorage()


@pytest.fixture
async def flaky_client(
    issuer: StubTokenIssuer, store: InMemoryStore, clock: SteppingClock, flaky: UnavailableStorage
) -> AsyncIterator[httpx.AsyncClient]:
    app: FastAPI = build_test_app(issuer, lambda: InMemoryUnitOfWork(store), clock, flaky)
    async with http_client(app) as client:
        yield client


async def test_when_storage_is_down_uploads_are_a_503_and_the_product_is_untouched(
    flaky_client: httpx.AsyncClient, admin: dict[str, str], flaky: UnavailableStorage
) -> None:
    await create_product(flaky_client, admin)
    flaky.down = True

    response = await put_image(flaky_client, admin, images.jpeg())

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "1"
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["title"] == "Image storage unavailable"
    assert (await flaky_client.get("/api/v1/products/RS-001")).json()["version"] == 1


async def test_when_storage_is_down_everything_else_keeps_working(
    flaky_client: httpx.AsyncClient, admin: dict[str, str], flaky: UnavailableStorage
) -> None:
    flaky.down = True

    created = await flaky_client.post("/api/v1/products", json=valid_product(), headers=admin)
    listing = await flaky_client.get("/api/v1/products")
    search = await flaky_client.get("/api/v1/products", params={"q": "running"})

    assert (created.status_code, listing.status_code, search.status_code) == (201, 200, 200)


async def test_removing_an_image_still_succeeds_when_storage_is_down(
    flaky_client: httpx.AsyncClient, admin: dict[str, str], flaky: UnavailableStorage
) -> None:
    await create_product(flaky_client, admin)
    await put_image(flaky_client, admin, images.jpeg())
    flaky.down = True

    response = await flaky_client.delete(IMAGE_URL, headers=admin | {"If-Match": '"2"'})

    assert response.status_code == 200
    assert response.json()["image_url"] is None


async def test_the_openapi_document_describes_the_multipart_upload(
    client: httpx.AsyncClient,
) -> None:
    spec = (await client.get("/openapi.json")).json()

    put = spec["paths"]["/api/v1/products/{sku}/image"]["put"]
    schema = put["requestBody"]["content"]["multipart/form-data"]["schema"]
    assert schema["required"] == ["file"]
    assert {"401", "403", "404", "412", "413", "415", "422", "428", "503"} <= set(put["responses"])
    delete = spec["paths"]["/api/v1/products/{sku}/image"]["delete"]
    assert {"200", "404", "412", "428"} <= set(delete["responses"])
    product = spec["components"]["schemas"]["ProductOut"]["properties"]
    assert {"image_url", "thumbnail_url"} <= set(product)


def test_the_app_fixture_wires_the_in_memory_storage(app: FastAPI) -> None:
    assert app.state.media_urls is not None
