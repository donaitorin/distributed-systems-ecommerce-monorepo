import io
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import httpx
import pytest
from catalog_testing import images
from catalog_testing.support import bearer, build_test_app, http_client, valid_product
from PIL import Image
from sqlalchemy import text

from catalog.domain.image import IMMUTABLE_CACHE_CONTROL
from catalog.infra.database import create_engine, create_session_factory
from catalog.infra.unit_of_work import SqlAlchemyUnitOfWork
from ecommerce_auth import Role
from ecommerce_auth.testing import StubTokenIssuer
from ecommerce_storage import S3ObjectStorage, S3Settings, build_s3_client
from seaweedfs_support import SeaweedFs

pytestmark = pytest.mark.integration


class Environment:
    def __init__(self, client: httpx.AsyncClient, admin: dict[str, str], server: SeaweedFs) -> None:
        self.client = client
        self.admin = admin
        self.server = server
        self.s3 = build_s3_client(server.settings)
        self.failing_commit = False

    def keys_of(self, sku: str) -> list[str]:
        listing = self.s3.list_objects_v2(Bucket="media", Prefix=f"products/{sku}/")
        return sorted(item["Key"] for item in listing.get("Contents", []))

    async def create(self, sku: str) -> None:
        response = await self.client.post(
            "/api/v1/products", json=valid_product(sku=sku), headers=self.admin
        )
        assert response.status_code == 201

    async def put(self, sku: str, data: bytes, if_match: str = "*") -> httpx.Response:
        body, content_type = images.multipart([("file", "photo.jpg", data, "image/jpeg")])
        return await self.client.put(
            f"/api/v1/products/{sku}/image",
            content=body,
            headers=self.admin | {"Content-Type": content_type, "If-Match": if_match},
        )

    async def fetch(self, url: str) -> httpx.Response:
        async with httpx.AsyncClient() as anonymous:
            return await anonymous.get(url)


@pytest.fixture
async def environment(
    migrated_database_url: str,
    seaweedfs: SeaweedFs,
    issuer: StubTokenIssuer,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[Environment]:
    engine = create_engine(migrated_database_url)
    factory = create_session_factory(engine)
    storage = S3ObjectStorage(
        build_s3_client(seaweedfs.settings), seaweedfs.media_bucket, seaweedfs.public_base_url
    )
    app = build_test_app(issuer, lambda: SqlAlchemyUnitOfWork(factory), storage=storage)
    original_commit = SqlAlchemyUnitOfWork.commit
    holder: dict[str, Environment] = {}

    async def commit(self: SqlAlchemyUnitOfWork) -> None:
        if holder["environment"].failing_commit:
            raise RuntimeError("database went away")
        await original_commit(self)

    monkeypatch.setattr(SqlAlchemyUnitOfWork, "commit", commit)
    async with http_client(app) as client:
        holder["environment"] = Environment(client, bearer(issuer, Role.ADMIN), seaweedfs)
        yield holder["environment"]
    await engine.dispose()


def decode(data: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(data))
    image.load()
    return image


def unique_sku(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:8].upper()}"


async def test_an_uploaded_image_is_served_publicly_as_two_cacheable_webp_renditions(
    environment: Environment,
) -> None:
    sku = unique_sku("IMG")
    await environment.create(sku)

    response = await environment.put(
        sku, images.jpeg_with_metadata(orientation=6, size=(2400, 1600))
    )

    body = response.json()
    assert response.status_code == 200
    full = await environment.fetch(body["image_url"])
    thumbnail = await environment.fetch(body["thumbnail_url"])
    for served in (full, thumbnail):
        assert served.status_code == 200
        assert served.headers["Content-Type"] == "image/webp"
        assert served.headers["Cache-Control"] == IMMUTABLE_CACHE_CONTROL
        assert not decode(served.content).getexif()
        assert b"Secret Camera Co" not in served.content
    assert decode(full.content).size == (800, 1200)
    assert decode(thumbnail.content).size == (267, 400)
    assert len(environment.keys_of(sku)) == 2


async def test_replacing_the_image_gives_a_new_url_and_deletes_the_old_objects(
    environment: Environment,
) -> None:
    sku = unique_sku("REP")
    await environment.create(sku)
    first = (await environment.put(sku, images.jpeg())).json()

    second = (await environment.put(sku, images.png(), if_match='"2"')).json()

    assert second["image_url"] != first["image_url"]
    assert (await environment.fetch(first["image_url"])).status_code == 404
    assert (await environment.fetch(first["thumbnail_url"])).status_code == 404
    assert (await environment.fetch(second["image_url"])).status_code == 200
    assert len(environment.keys_of(sku)) == 2


async def test_deleting_the_image_removes_both_objects_and_the_urls(
    environment: Environment,
) -> None:
    sku = unique_sku("DEL")
    await environment.create(sku)
    uploaded = (await environment.put(sku, images.webp())).json()

    response = await environment.client.delete(
        f"/api/v1/products/{sku}/image", headers=environment.admin | {"If-Match": '"2"'}
    )

    assert response.status_code == 200
    assert response.json()["image_url"] is None
    assert (await environment.fetch(uploaded["image_url"])).status_code == 404
    assert environment.keys_of(sku) == []


async def test_a_failed_commit_leaves_no_new_objects_and_keeps_the_previous_image(
    environment: Environment,
) -> None:
    sku = unique_sku("ORP")
    await environment.create(sku)
    kept = (await environment.put(sku, images.jpeg())).json()
    keys_before = environment.keys_of(sku)
    environment.failing_commit = True

    response = await environment.put(sku, images.png(), if_match='"2"')
    environment.failing_commit = False

    assert response.status_code == 500
    assert environment.keys_of(sku) == keys_before
    assert (await environment.fetch(kept["image_url"])).status_code == 200
    current = (await environment.client.get(f"/api/v1/products/{sku}")).json()
    assert current["image_url"] == kept["image_url"]
    assert current["version"] == 2


async def test_a_conflicting_upload_leaves_the_bucket_untouched(
    environment: Environment,
) -> None:
    sku = unique_sku("CON")
    await environment.create(sku)

    response = await environment.put(sku, images.jpeg(), if_match='"5"')

    assert response.status_code == 412
    assert environment.keys_of(sku) == []


async def test_the_product_row_stores_the_key_stem_and_never_a_url(
    environment: Environment, migrated_database_url: str
) -> None:
    sku = unique_sku("KEY")
    await environment.create(sku)
    body = (await environment.put(sku, images.jpeg())).json()
    engine = create_engine(migrated_database_url)
    try:
        async with engine.connect() as connection:
            stored: Any = await connection.scalar(
                text("SELECT image_key FROM products WHERE sku = :sku"), {"sku": sku}
            )
    finally:
        await engine.dispose()

    assert stored.startswith(f"products/{sku}/")
    assert "://" not in stored
    assert not stored.endswith(".webp")
    assert body["image_url"].endswith(f"{stored}-1200.webp")


async def test_an_unreachable_object_store_is_a_503_and_leaves_the_product_alone(
    migrated_database_url: str, issuer: StubTokenIssuer
) -> None:
    engine = create_engine(migrated_database_url)
    factory = create_session_factory(engine)
    broken = S3ObjectStorage(
        build_s3_client(
            S3Settings("a", "s", endpoint_url="http://127.0.0.1:1", connect_timeout_seconds=0.5)
        ),
        "media",
        "http://127.0.0.1:1/media",
    )
    app = build_test_app(issuer, lambda: SqlAlchemyUnitOfWork(factory), storage=broken)
    admin = bearer(issuer, Role.ADMIN)
    sku = unique_sku("DWN")
    try:
        async with http_client(app) as client:
            await client.post("/api/v1/products", json=valid_product(sku=sku), headers=admin)
            body, content_type = images.multipart([("file", "a.jpg", images.jpeg(), "image/jpeg")])

            response = await client.put(
                f"/api/v1/products/{sku}/image",
                content=body,
                headers=admin | {"Content-Type": content_type, "If-Match": "*"},
            )
            product = (await client.get(f"/api/v1/products/{sku}")).json()
    finally:
        await engine.dispose()

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "1"
    assert product["version"] == 1
    assert product["image_url"] is None
