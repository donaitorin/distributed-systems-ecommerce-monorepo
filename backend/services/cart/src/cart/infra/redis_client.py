from redis.asyncio import Redis

from cart.settings import RedisSettings

SOCKET_TIMEOUT_SECONDS = 2.0
HEALTH_CHECK_INTERVAL_SECONDS = 30


def create_redis(settings: RedisSettings) -> Redis:
    return Redis(
        host=settings.host,
        port=settings.port,
        password=settings.password,
        decode_responses=True,
        socket_timeout=SOCKET_TIMEOUT_SECONDS,
        socket_connect_timeout=SOCKET_TIMEOUT_SECONDS,
        health_check_interval=HEALTH_CHECK_INTERVAL_SECONDS,
    )
