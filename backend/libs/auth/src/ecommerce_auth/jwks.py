import asyncio
import time
from collections.abc import Callable
from typing import Any, Protocol

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from jwt.algorithms import RSAAlgorithm

from ecommerce_auth.errors import KeysUnavailableError
from ecommerce_auth.settings import JwtSettings


class SigningKeyProvider(Protocol):
    async def get_key(self, kid: str) -> RSAPublicKey: ...


class JwksClient:
    def __init__(
        self,
        settings: JwtSettings,
        http_client: httpx.AsyncClient,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._settings = settings
        self._http_client = http_client
        self._clock = clock
        self._keys: dict[str, RSAPublicKey] = {}
        self._last_attempt_at: float | None = None
        self._last_success_at: float | None = None
        self._lock = asyncio.Lock()

    async def get_key(self, kid: str) -> RSAPublicKey:
        async with self._lock:
            if self._should_refetch(kid):
                await self._refetch()
            if not self._keys:
                raise KeysUnavailableError("Signing keys could not be retrieved")
            key = self._keys.get(kid)
        if key is None:
            raise jwt.InvalidKeyError(f"unknown signing key: {kid}")
        return key

    def _should_refetch(self, kid: str) -> bool:
        now = self._clock()
        cooldown = self._settings.keys_refetch_cooldown_seconds
        if self._last_attempt_at is not None and now - self._last_attempt_at < cooldown:
            return False
        if self._last_success_at is None:
            return True
        expired = now - self._last_success_at >= self._settings.keys_cache_ttl_seconds
        return expired or kid not in self._keys

    async def _refetch(self) -> None:
        self._last_attempt_at = self._clock()
        try:
            response = await self._http_client.get(
                self._settings.jwks_url, timeout=self._settings.request_timeout_seconds
            )
            response.raise_for_status()
            keys = _parse_keys(response.json())
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError, jwt.PyJWTError):
            return
        self._keys = keys
        self._last_success_at = self._last_attempt_at


def _parse_keys(document: dict[str, Any]) -> dict[str, RSAPublicKey]:
    keys: dict[str, RSAPublicKey] = {}
    for jwk in document["keys"]:
        if jwk.get("kty") != "RSA" or "kid" not in jwk:
            continue
        key = RSAAlgorithm.from_jwk(jwk)
        if isinstance(key, RSAPublicKey):
            keys[jwk["kid"]] = key
    return keys
