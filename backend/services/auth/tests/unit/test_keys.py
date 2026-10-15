import base64
import hashlib
import json
import os
import stat
from pathlib import Path

import pytest
from auth_testing.support import new_signing_key
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from jwt.algorithms import RSAAlgorithm

from auth.infra.keys import KeyStore, KeyStoreError, generate_key_file, load_key_store, thumbprint


def test_kid_is_the_rfc7638_thumbprint_of_the_public_key() -> None:
    key = new_signing_key()
    jwk = RSAAlgorithm.to_jwk(key.private_key.public_key(), as_dict=True)
    canonical = json.dumps(
        {"e": jwk["e"], "kty": "RSA", "n": jwk["n"]}, separators=(",", ":"), sort_keys=True
    )
    expected = base64.urlsafe_b64encode(hashlib.sha256(canonical.encode()).digest())

    assert key.kid == expected.rstrip(b"=").decode()
    assert thumbprint(key.private_key) == key.kid


def test_public_jwk_has_no_private_material() -> None:
    jwk = new_signing_key().public_jwk()

    assert jwk["kty"] == "RSA"
    assert jwk["use"] == "sig"
    assert jwk["alg"] == "RS256"
    assert not {"d", "p", "q", "dp", "dq", "qi"} & set(jwk)


def test_jwks_lists_every_key_so_a_rotation_can_overlap() -> None:
    old, new = new_signing_key(), new_signing_key()

    store = KeyStore([old, new], new.kid)

    assert [item["kid"] for item in store.jwks_document()["keys"]] == [old.kid, new.kid]
    assert store.active.kid == new.kid


def test_an_unknown_active_key_is_an_error() -> None:
    with pytest.raises(KeyStoreError, match="active signing key"):
        KeyStore([new_signing_key()], "missing")


def test_generate_writes_a_private_pem_named_after_the_kid(tmp_path: Path) -> None:
    key = generate_key_file(tmp_path / "keys")

    path = tmp_path / "keys" / f"{key.kid}.pem"
    assert path.read_bytes().startswith(b"-----BEGIN PRIVATE KEY-----")
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_loading_returns_the_keys_that_were_generated(tmp_path: Path) -> None:
    key = generate_key_file(tmp_path)

    store = load_key_store(tmp_path)

    assert store.kids == [key.kid]
    assert store.active.kid == key.kid


def test_an_empty_directory_fails_unless_generation_is_allowed(tmp_path: Path) -> None:
    with pytest.raises(KeyStoreError, match="no signing keys"):
        load_key_store(tmp_path)
    assert list(tmp_path.glob("*.pem")) == []


def test_a_missing_directory_fails_unless_generation_is_allowed(tmp_path: Path) -> None:
    with pytest.raises(KeyStoreError, match="no signing keys"):
        load_key_store(tmp_path / "absent")


def test_generation_when_missing_creates_the_directory_and_one_key(tmp_path: Path) -> None:
    store = load_key_store(tmp_path / "new", generate_if_missing=True)

    assert len(store.kids) == 1
    assert (tmp_path / "new" / f"{store.active.kid}.pem").exists()


def test_generation_is_not_repeated_when_keys_exist(tmp_path: Path) -> None:
    generate_key_file(tmp_path)

    store = load_key_store(tmp_path, generate_if_missing=True)

    assert len(store.kids) == 1


def test_the_newest_file_signs_by_default(tmp_path: Path) -> None:
    old = generate_key_file(tmp_path)
    new = generate_key_file(tmp_path)
    os.utime(tmp_path / f"{old.kid}.pem", (1_000, 1_000))
    os.utime(tmp_path / f"{new.kid}.pem", (2_000, 2_000))

    store = load_key_store(tmp_path)

    assert sorted(store.kids) == sorted([old.kid, new.kid])
    assert store.active.kid == new.kid


def test_the_active_kid_overrides_the_newest_file(tmp_path: Path) -> None:
    old = generate_key_file(tmp_path)
    new = generate_key_file(tmp_path)
    os.utime(tmp_path / f"{old.kid}.pem", (1_000, 1_000))
    os.utime(tmp_path / f"{new.kid}.pem", (2_000, 2_000))

    assert load_key_store(tmp_path, active_kid=old.kid).active.kid == old.kid


def test_non_rsa_keys_are_rejected(tmp_path: Path) -> None:
    pem = ec.generate_private_key(ec.SECP256R1()).private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    (tmp_path / "ec.pem").write_bytes(pem)

    with pytest.raises(KeyStoreError, match="RSA"):
        load_key_store(tmp_path)


def test_other_files_in_the_directory_are_ignored(tmp_path: Path) -> None:
    generate_key_file(tmp_path)
    (tmp_path / "README.txt").write_text("not a key")

    assert len(load_key_store(tmp_path).kids) == 1
