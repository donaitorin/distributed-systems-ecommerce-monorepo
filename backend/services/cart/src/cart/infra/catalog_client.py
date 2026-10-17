import asyncio
from decimal import Decimal
from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from cart.application.errors import CatalogCircuitOpenError, CatalogUnavailableError
from cart.domain.product import ProductState
from ecommerce_resilience import (
    CircuitBreaker,
    CircuitOpenError,
    ReadRetryPolicy,
    retry_idempotent_read,
)
from ecommerce_resilience.retry import Sleeper
from ecommerce_storage import image_key_from_full_url

TRANSIENT_STATUSES = frozenset(
    {HTTPStatus.BAD_GATEWAY, HTTPStatus.SERVICE_UNAVAILABLE, HTTPStatus.GATEWAY_TIMEOUT}
)
OVERLOADED_STATUSES = frozenset({HTTPStatus.TOO_MANY_REQUESTS})
CIRCUIT_NAME = "catalog"


class CatalogCallError(Exception):
    def __init__(self, message: str, transient: bool, trips_breaker: bool) -> None:
        super().__init__(message)
        self.transient = transient
        self.trips_breaker = trips_breaker


def is_transient(error: BaseException) -> bool:
    return isinstance(error, CatalogCallError) and error.transient


def trips_breaker(error: BaseException) -> bool:
    return isinstance(error, CatalogCallError) and error.trips_breaker


class HttpCatalogGateway:
    def __init__(
        self,
        client: httpx.AsyncClient,
        media_public_base_url: str,
        breaker: CircuitBreaker | None = None,
        retry: ReadRetryPolicy | None = None,
        sleep: Sleeper = asyncio.sleep,
    ) -> None:
        self._client = client
        self._media_base = media_public_base_url
        self._breaker = breaker or CircuitBreaker(CIRCUIT_NAME)
        self._retry = retry or ReadRetryPolicy()
        self._sleep = sleep

    async def get(self, sku: str) -> ProductState | None:
        try:
            return await self._breaker.call(lambda: self._read(sku), is_failure=trips_breaker)
        except CircuitOpenError as error:
            raise CatalogCircuitOpenError(error.retry_after_whole_seconds) from error
        except CatalogCallError as error:
            raise CatalogUnavailableError(str(error)) from error

    async def _read(self, sku: str) -> ProductState | None:
        return await retry_idempotent_read(
            lambda: self._fetch(sku), self._retry, is_transient, self._sleep
        )

    async def _fetch(self, sku: str) -> ProductState | None:
        try:
            response = await self._client.get(f"/api/v1/products/{quote(sku, safe='')}")
        except httpx.HTTPError as error:
            raise CatalogCallError(
                f"catalog request failed: {type(error).__name__}",
                transient=not isinstance(error, httpx.ReadTimeout),
                trips_breaker=True,
            ) from error
        if response.status_code == HTTPStatus.NOT_FOUND:
            return None
        if response.status_code != HTTPStatus.OK:
            status = HTTPStatus(response.status_code)
            raise CatalogCallError(
                f"catalog answered {response.status_code}",
                transient=status in TRANSIENT_STATUSES,
                trips_breaker=status >= HTTPStatus.INTERNAL_SERVER_ERROR
                or status in OVERLOADED_STATUSES,
            )
        try:
            return self._parse(response.json())
        except (KeyError, TypeError, ValueError, ArithmeticError) as error:
            raise CatalogCallError(
                "catalog answered an unexpected body", transient=False, trips_breaker=True
            ) from error

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
