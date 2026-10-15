import pytest
from auth_testing.support import FAST_HASHING

from auth.infra.hashing import Argon2idHasher, HashingSettings


@pytest.fixture
def hasher() -> Argon2idHasher:
    return Argon2idHasher(FAST_HASHING)


async def test_hashes_are_argon2id_with_the_configured_parameters(hasher: Argon2idHasher) -> None:
    password_hash = await hasher.hash("correct horse battery")

    assert password_hash.startswith("$argon2id$")
    assert "m=8,t=1,p=1" in password_hash


async def test_the_default_parameters_follow_the_owasp_minimum() -> None:
    password_hash = await Argon2idHasher().hash("correct horse battery")

    assert "m=19456,t=2,p=1" in password_hash


async def test_the_same_password_gets_a_different_salt_each_time(hasher: Argon2idHasher) -> None:
    assert await hasher.hash("same password") != await hasher.hash("same password")


async def test_the_right_password_verifies(hasher: Argon2idHasher) -> None:
    password_hash = await hasher.hash("correct horse battery")

    assert await hasher.verify(password_hash, "correct horse battery") is True


async def test_a_wrong_password_does_not_verify(hasher: Argon2idHasher) -> None:
    password_hash = await hasher.hash("correct horse battery")

    assert await hasher.verify(password_hash, "wrong horse battery") is False


async def test_a_malformed_hash_does_not_verify_instead_of_raising(hasher: Argon2idHasher) -> None:
    assert await hasher.verify("not-a-hash", "anything") is False


async def test_the_decoy_check_takes_the_same_path_without_raising(hasher: Argon2idHasher) -> None:
    await hasher.verify_decoy("whatever the caller typed")


async def test_hashes_made_with_weaker_parameters_need_a_rehash(hasher: Argon2idHasher) -> None:
    old_hash = await hasher.hash("correct horse battery")
    stronger = Argon2idHasher(HashingSettings(memory_cost_kib=16, time_cost=2, parallelism=1))

    assert stronger.needs_rehash(old_hash) is True
    assert hasher.needs_rehash(old_hash) is False


async def test_concurrent_hashing_is_bounded_but_completes() -> None:
    import asyncio

    hasher = Argon2idHasher(HashingSettings(memory_cost_kib=8, time_cost=1, concurrency=2))

    hashes = await asyncio.gather(*(hasher.hash(f"password number {n}") for n in range(6)))

    assert len(set(hashes)) == 6
