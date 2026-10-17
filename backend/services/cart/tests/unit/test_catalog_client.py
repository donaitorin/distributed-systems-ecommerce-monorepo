from collections.abc import Callable
from decimal import Decimal
from typing import Any

import httpx
import pytest
from cart_testing.support import IMAGE_KEY

from cart.application.errors import CatalogUnavailableError
from cart.infra.catalog_client import HttpCatalogGateway

BODY: dict[str, Any] = {
    "sku": "RS-001",
    "name": "Running Shoes",
    "description": "Lightweight",
    "category": None,
    "price": "89.99",
    "stock": 12,
    "weight_kg": None,
    "image_url": f"/media/{IMAGE_KEY}-1200.webp",
    "thumbnail_url": f"/media/{IMAGE_KEY}-400.webp",
    "version": 4,
    "created_at": "2026-10-16T10:00:00Z",
    "updated_at": "2026-10-16T10:00:00Z",
}


def gateway(
    handler: Callable[[httpx.Request], httpx.Response], media: str = "/media"
) -> HttpCatalogGateway:
    client = httpx.AsyncClient(
        base_url="http://catalog.test", transport=httpx.MockTransport(handler)
    )
    return HttpCatalogGateway(client, media)


async def test_a_product_is_read_with_its_version_and_image_key() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=BODY)

    product = await gateway(handler).get("RS-001")

    assert product is not None
    assert (product.sku, product.price, product.stock, product.version) == (
        "RS-001",
        Decimal("89.99"),
        12,
        4,
    )
    assert (product.deleted, product.image_key) == (False, IMAGE_KEY)
    assert seen[0].url.path == "/api/v1/products/RS-001"


async def test_a_product_without_an_image_has_no_key() -> None:
    body = BODY | {"image_url": None, "thumbnail_url": None}

    product = await gateway(lambda request: httpx.Response(200, json=body)).get("RS-001")

    assert product is not None
    assert product.image_key is None


async def test_an_image_under_another_base_url_is_treated_as_no_image() -> None:
    product = await gateway(lambda request: httpx.Response(200, json=BODY), "http://cdn/x").get(
        "RS-001"
    )

    assert product is not None
    assert product.image_key is None


async def test_a_404_means_there_is_no_such_product() -> None:
    assert await gateway(lambda request: httpx.Response(404, json={})).get("NOPE-1") is None


@pytest.mark.parametrize("status", [500, 502, 503, 429, 401])
async def test_any_other_status_is_a_catalog_outage(status: int) -> None:
    with pytest.raises(CatalogUnavailableError):
        await gateway(lambda request: httpx.Response(status)).get("RS-001")


async def test_a_timeout_or_a_refused_connection_is_a_catalog_outage() -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    def refused(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    for handler in (timeout, refused):
        with pytest.raises(CatalogUnavailableError):
            await gateway(handler).get("RS-001")


@pytest.mark.parametrize(
    "body", [{"sku": "RS-001"}, {**BODY, "price": "free"}, {**BODY, "stock": "many"}]
)
async def test_a_body_that_does_not_look_like_a_product_is_a_catalog_outage(
    body: dict[str, Any],
) -> None:
    with pytest.raises(CatalogUnavailableError):
        await gateway(lambda request: httpx.Response(200, json=body)).get("RS-001")


async def test_the_sku_is_escaped_in_the_path() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(404)

    await gateway(handler).get("A/B?C")

    assert seen[0].url.raw_path == b"/api/v1/products/A%2FB%3FC"
