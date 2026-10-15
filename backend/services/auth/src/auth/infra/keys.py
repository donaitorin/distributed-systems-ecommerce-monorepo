import base64
import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

KEY_SIZE_BITS = 2048
PEM_SUFFIX = ".pem"


class KeyStoreError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class SigningKey:
    kid: str
    private_key: rsa.RSAPrivateKey

    def public_jwk(self) -> dict[str, Any]:
        jwk = RSAAlgorithm.to_jwk(self.private_key.public_key(), as_dict=True)
        return {**jwk, "kid": self.kid, "use": "sig", "alg": "RS256"}


def thumbprint(private_key: rsa.RSAPrivateKey) -> str:
    jwk = RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    canonical = json.dumps(
        {"e": jwk["e"], "kty": jwk["kty"], "n": jwk["n"]}, separators=(",", ":"), sort_keys=True
    )
    digest = hashlib.sha256(canonical.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def signing_key_from(private_key: rsa.RSAPrivateKey) -> SigningKey:
    return SigningKey(thumbprint(private_key), private_key)


class KeyStore:
    def __init__(self, keys: Sequence[SigningKey], active_kid: str) -> None:
        by_kid = {key.kid: key for key in keys}
        if active_kid not in by_kid:
            raise KeyStoreError(f"active signing key {active_kid} is not in the key directory")
        self._keys = by_kid
        self.active = by_kid[active_kid]

    def jwks_document(self) -> dict[str, Any]:
        return {"keys": [key.public_jwk() for key in self._keys.values()]}

    def public_key(self, kid: str) -> rsa.RSAPublicKey:
        key = self._keys.get(kid)
        if key is None:
            raise jwt.InvalidKeyError(f"unknown signing key: {kid}")
        return key.private_key.public_key()

    @property
    def kids(self) -> list[str]:
        return list(self._keys)


class LocalKeyProvider:
    def __init__(self, store: KeyStore) -> None:
        self._store = store

    async def get_key(self, kid: str) -> rsa.RSAPublicKey:
        return self._store.public_key(kid)


def generate_key_file(directory: Path) -> SigningKey:
    directory.mkdir(parents=True, exist_ok=True)
    key = signing_key_from(rsa.generate_private_key(public_exponent=65537, key_size=KEY_SIZE_BITS))
    path = directory / f"{key.kid}{PEM_SUFFIX}"
    path.write_bytes(
        key.private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    path.chmod(0o600)
    return key


def _load_files(directory: Path) -> list[tuple[float, SigningKey]]:
    loaded: list[tuple[float, SigningKey]] = []
    for path in sorted(directory.glob(f"*{PEM_SUFFIX}")):
        private_key = serialization.load_pem_private_key(path.read_bytes(), password=None)
        if not isinstance(private_key, rsa.RSAPrivateKey):
            raise KeyStoreError(f"{path.name} does not hold an RSA private key")
        loaded.append((path.stat().st_mtime, signing_key_from(private_key)))
    return loaded


def load_key_store(
    directory: Path, active_kid: str | None = None, generate_if_missing: bool = False
) -> KeyStore:
    loaded = _load_files(directory) if directory.is_dir() else []
    if not loaded:
        if not generate_if_missing:
            raise KeyStoreError(f"no signing keys found in {directory}")
        generate_key_file(directory)
        loaded = _load_files(directory)
    keys = [key for _, key in loaded]
    chosen = active_kid or max(loaded, key=lambda item: (item[0], item[1].kid))[1].kid
    return KeyStore(keys, chosen)
