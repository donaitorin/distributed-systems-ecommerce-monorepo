from decimal import Decimal
from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from cart.application.errors import CatalogUnavailableError
from cart.domain.product import ProductState
from ecommerce_storage import image_key_from_full_url


class HttpCatalogGateway:
    def __init__(self, client: httpx.AsyncClient, media_public_base_url: str) -> None:
        self._client = client
        self._media_base = media_public_base_url

    async def get(self, sku: str) -> ProductState | None:
        try:
            response = await self._client.get(f"/api/v1/products/{quote(sku, safe='')}")
        except httpx.HTTPError as error:
            raise CatalogUnavailableError(f"catalog request failed: {error!r}") from error
        if response.status_code == HTTPStatus.NOT_FOUND:
            return None
        if response.status_code != HTTPStatus.OK:
            raise CatalogUnavailableError(f"catalog answered {response.status_code}")
        try:
            return self._parse(response.json())
        except (KeyError, TypeError, ValueError, ArithmeticError) as error:
            raise CatalogUnavailableError("catalog answered an unexpected body") from error

    def _parse(self, body: dict[str, Any]) -> ProductState:
        image_url = body.get("image_url")
        return ProductState(
            sku=body["sku"],
            name=body["name"],
            price=Decimal(body["price"]),
            stock=int(body["stock"]),
            version=int(body["version"]),
            deleted=False,
            image_key=(image_key_from_full_url(self._media_base, image_url) if image_url else None),
        )
