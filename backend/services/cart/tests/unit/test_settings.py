import pytest

from cart.settings import CART_TTL_SECONDS, CartSettings
from ecommerce_resilience import BreakerConfig, ReadRetryPolicy

ENVIRONMENT = {
    "REDIS_CART_HOST": "redis-cart",
    "REDIS_CART_PASSWORD": "secret",
    "JWT_JWKS_URL": "http://auth/jwks.json",
    "JWT_ISSUER": "ecommerce-auth",
    "JWT_AUDIENCE": "ecommerce-api",
}


def test_the_defaults_match_the_compose_network() -> None:
    settings = CartSettings.from_env(ENVIRONMENT)

    assert (settings.redis.host, settings.redis.port, settings.redis.password) == (
        "redis-cart",
        6379,
        "secret",
    )
    assert settings.catalog_base_url == "http://catalog:8000"
    assert settings.catalog_timeout_seconds == 2.0
    assert settings.catalog_breaker == BreakerConfig(5, 10.0, 1)
    assert settings.catalog_retry == ReadRetryPolicy(2, 0.1, 0.5)
    assert settings.media_public_base_url == "/media"
    assert settings.ttl_seconds == CART_TTL_SECONDS == 30 * 24 * 3600
    assert (settings.log_level, settings.root_path) == ("INFO", "")


def test_every_value_can_be_overridden() -> None:
    settings = CartSettings.from_env(
        ENVIRONMENT
        | {
            "REDIS_CART_PORT": "16379",
            "CATALOG_BASE_URL": "http://localhost:9",
            "CATALOG_TIMEOUT_SECONDS": "0.5",
            "CATALOG_BREAKER_FAILURE_THRESHOLD": "3",
            "CATALOG_BREAKER_OPEN_SECONDS": "20",
            "CATALOG_BREAKER_HALF_OPEN_PROBES": "2",
            "CATALOG_RETRY_ATTEMPTS": "4",
            "CATALOG_RETRY_INITIAL_DELAY_SECONDS": "0.2",
            "CATALOG_RETRY_MAX_DELAY_SECONDS": "1.5",
            "MEDIA_PUBLIC_BASE_URL": "http://cdn/media",
            "CART_TTL_SECONDS": "60",
            "LOG_LEVEL": "DEBUG",
            "ROOT_PATH": "/cart-service",
        }
    )

    assert settings.redis.port == 16379
    assert settings.catalog_base_url == "http://localhost:9"
    assert settings.catalog_timeout_seconds == 0.5
    assert settings.catalog_breaker == BreakerConfig(3, 20.0, 2)
    assert settings.catalog_retry == ReadRetryPolicy(4, 0.2, 1.5)
    assert settings.media_public_base_url == "http://cdn/media"
    assert settings.ttl_seconds == 60
    assert (settings.log_level, settings.root_path) == ("DEBUG", "/cart-service")


@pytest.mark.parametrize("missing", ["REDIS_CART_HOST", "REDIS_CART_PASSWORD", "JWT_JWKS_URL"])
def test_the_redis_and_jwt_settings_are_required(missing: str) -> None:
    environment = {key: value for key, value in ENVIRONMENT.items() if key != missing}

    with pytest.raises(KeyError):
        CartSettings.from_env(environment)


@pytest.mark.parametrize(
    "override",
    [
        {"CATALOG_BREAKER_FAILURE_THRESHOLD": "0"},
        {"CATALOG_BREAKER_OPEN_SECONDS": "0"},
        {"CATALOG_BREAKER_HALF_OPEN_PROBES": "0"},
        {"CATALOG_RETRY_ATTEMPTS": "0"},
        {"CATALOG_RETRY_INITIAL_DELAY_SECONDS": "2", "CATALOG_RETRY_MAX_DELAY_SECONDS": "1"},
    ],
)
def test_an_invalid_resilience_setting_stops_the_service_at_startup(
    override: dict[str, str],
) -> None:
    with pytest.raises(ValueError, match="must"):
        CartSettings.from_env(ENVIRONMENT | override)
