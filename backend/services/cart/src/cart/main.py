import os
from collections.abc import Awaitable, Callable
from datetime import datetime

import httpx
from fastapi import FastAPI
from redis.asyncio import Redis

from cart.api import install_api
from cart.application.carts import CartService
from cart.application.clock import utc_now
from cart.application.ports import CartStore, CatalogGateway, ProductProjection
from cart.infra.catalog_client import CIRCUIT_NAME, HttpCatalogGateway
from cart.infra.redis_client import create_redis
from cart.infra.redis_projection import RedisProductProjection
from cart.infra.redis_store import RedisCartStore
from cart.settings import CartSettings
from ecommerce_auth import create_token_verifier
from ecommerce_resilience import CircuitBreaker, LoggingListener
from ecommerce_web import ReadinessCheck, ServiceSettings, create_app

SERVICE_NAME = "cart"


def redis_readiness_check(redis: Redis) -> ReadinessCheck:
    async def probe() -> None:
        await redis.ping()

    return ReadinessCheck("redis", probe)


def create_cart_app(
    settings: CartSettings,
    redis: Redis | None = None,
    store: CartStore | None = None,
    projection: ProductProjection | None = None,
    catalog: CatalogGateway | None = None,
    clock: Callable[[], datetime] = utc_now,
) -> FastAPI:
    redis = redis or create_redis(settings.redis)
    shutdown: list[Callable[[], Awaitable[None]]] = [redis.aclose]
    if catalog is None:
        client = httpx.AsyncClient(
            base_url=settings.catalog_base_url, timeout=settings.catalog_timeout_seconds
        )
        shutdown.append(client.aclose)
        breaker = CircuitBreaker(CIRCUIT_NAME, settings.catalog_breaker, LoggingListener())
        catalog = HttpCatalogGateway(
            client, settings.media_public_base_url, breaker, settings.catalog_retry
        )
    app = create_app(
        ServiceSettings(name=SERVICE_NAME, log_level=settings.log_level),
        readiness_checks=[redis_readiness_check(redis)],
        token_verifier=create_token_verifier(settings.jwt),
        on_shutdown=shutdown,
        root_path=settings.root_path,
    )
    app.state.media_base_url = settings.media_public_base_url
    app.state.cart_service = CartService(
        store or RedisCartStore(redis, settings.ttl_seconds),
        projection or RedisProductProjection(redis, settings.ttl_seconds),
        catalog,
        clock,
    )
    install_api(app)
    return app


def build() -> FastAPI:
    return create_cart_app(CartSettings.from_env(os.environ))
