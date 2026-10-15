from datetime import timedelta

import jwt
import pytest
from auth_testing.support import (
    AUDIENCE,
    ISSUER,
    STRONG_PASSWORD,
    FakeHasher,
    SteppingClock,
    new_signing_key,
)

from auth.application.errors import (
    EmailTakenError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
)
from auth.application.registration import RegistrationService
from auth.application.service import AuthService, RefreshPolicy, TokenPair, hash_refresh_token
from auth.domain.errors import ValidationFailedError
from auth.domain.tokens import REUSE_GRACE, RefreshTokenRecord
from auth.domain.user import Role
from auth.infra.keys import KeyStore
from auth.infra.memory import InMemoryStore, InMemoryUnitOfWork
from auth.infra.signer import JwtAccessTokenIssuer

EMAIL = "ada@example.com"


class Harness:
    def __init__(self) -> None:
        self.store = InMemoryStore()
        self.clock = SteppingClock()
        self.hasher = FakeHasher()
        key = new_signing_key()
        issuer = JwtAccessTokenIssuer(
            KeyStore([key], key.kid), ISSUER, AUDIENCE, timedelta(minutes=15)
        )
        self.registration = RegistrationService(self.unit_of_work, self.hasher, self.clock)
        self.service = AuthService(self.unit_of_work, self.hasher, issuer, self.clock)

    def unit_of_work(self) -> InMemoryUnitOfWork:
        return InMemoryUnitOfWork(self.store)

    async def logged_in(self, email: str = EMAIL) -> TokenPair:
        await self.registration.register(email, STRONG_PASSWORD)
        return await self.service.login(email, STRONG_PASSWORD)

    def record_of(self, pair: TokenPair) -> RefreshTokenRecord:
        return self.store.refresh_tokens[hash_refresh_token(pair.refresh_token)].record

    def family_revoked(self, refresh_token: str) -> bool:
        stored = self.store.refresh_tokens[hash_refresh_token(refresh_token)]
        return stored.record.revoked_at is not None


@pytest.fixture
def harness() -> Harness:
    return Harness()


async def test_registration_stores_a_customer_with_a_normalized_email(harness: Harness) -> None:
    user = await harness.registration.register("  Ada@Example.COM ", STRONG_PASSWORD)

    assert user.email == EMAIL
    assert user.role is Role.CUSTOMER
    assert user.password_hash == f"fake${STRONG_PASSWORD}"
    assert user.created_at == harness.clock()


async def test_registration_can_create_an_admin_for_the_seed(harness: Harness) -> None:
    user = await harness.registration.register(EMAIL, STRONG_PASSWORD, Role.ADMIN)

    assert user.role is Role.ADMIN


async def test_the_same_email_in_another_case_is_already_taken(harness: Harness) -> None:
    await harness.registration.register(EMAIL, STRONG_PASSWORD)

    with pytest.raises(EmailTakenError):
        await harness.registration.register("ADA@example.com", STRONG_PASSWORD)


async def test_registration_validates_before_hashing(harness: Harness) -> None:
    with pytest.raises(ValidationFailedError):
        await harness.registration.register("nope", "short")

    assert harness.hasher.hash_calls == 0


async def test_login_returns_a_verifiable_access_token_and_an_opaque_refresh_token(
    harness: Harness,
) -> None:
    user = await harness.registration.register(EMAIL, STRONG_PASSWORD)

    pair = await harness.service.login("ADA@example.com", STRONG_PASSWORD)

    claims = jwt.decode(pair.access.value, options={"verify_signature": False})
    assert claims["sub"] == str(user.id)
    assert pair.access.expires_in == 900
    assert len(pair.refresh_token) >= 43


async def test_only_the_hash_of_the_refresh_token_is_stored(harness: Harness) -> None:
    pair = await harness.logged_in()

    stored = harness.store.refresh_tokens
    assert list(stored) == [hash_refresh_token(pair.refresh_token)]
    assert pair.refresh_token not in stored


async def test_each_login_starts_its_own_token_family(harness: Harness) -> None:
    first = await harness.logged_in()
    second = await harness.service.login(EMAIL, STRONG_PASSWORD)

    families = {item.record.family_id for item in harness.store.refresh_tokens.values()}
    assert len(families) == 2
    assert first.refresh_token != second.refresh_token


async def test_unknown_email_and_wrong_password_fail_with_the_same_error(
    harness: Harness,
) -> None:
    await harness.registration.register(EMAIL, STRONG_PASSWORD)

    with pytest.raises(InvalidCredentialsError) as unknown:
        await harness.service.login("nobody@example.com", STRONG_PASSWORD)
    with pytest.raises(InvalidCredentialsError) as wrong:
        await harness.service.login(EMAIL, "not the password")

    assert type(unknown.value) is type(wrong.value)
    assert str(unknown.value) == str(wrong.value)


async def test_an_unknown_email_still_pays_for_a_password_check(harness: Harness) -> None:
    with pytest.raises(InvalidCredentialsError):
        await harness.service.login("nobody@example.com", STRONG_PASSWORD)

    assert harness.hasher.decoy_calls == 1


async def test_a_known_email_does_not_use_the_decoy(harness: Harness) -> None:
    await harness.logged_in()

    assert harness.hasher.decoy_calls == 0


async def test_a_failed_login_issues_no_tokens(harness: Harness) -> None:
    await harness.registration.register(EMAIL, STRONG_PASSWORD)

    with pytest.raises(InvalidCredentialsError):
        await harness.service.login(EMAIL, "not the password")

    assert harness.store.refresh_tokens == {}


async def test_login_upgrades_a_hash_made_with_old_parameters(harness: Harness) -> None:
    user = await harness.registration.register(EMAIL, STRONG_PASSWORD)
    harness.hasher.rehash_needed = True
    hashes_before = harness.hasher.hash_calls

    await harness.service.login(EMAIL, STRONG_PASSWORD)

    assert harness.hasher.hash_calls == hashes_before + 1
    assert harness.store.users[user.id].password_hash == f"fake${STRONG_PASSWORD}"


async def test_login_leaves_a_current_hash_alone(harness: Harness) -> None:
    await harness.registration.register(EMAIL, STRONG_PASSWORD)
    hashes_before = harness.hasher.hash_calls

    await harness.service.login(EMAIL, STRONG_PASSWORD)

    assert harness.hasher.hash_calls == hashes_before


async def test_refresh_rotates_the_token_and_issues_a_new_access_token(harness: Harness) -> None:
    first = await harness.logged_in()
    harness.clock.advance(seconds=60)

    second = await harness.service.refresh(first.refresh_token)

    assert second.refresh_token != first.refresh_token
    assert second.access.value != first.access.value


async def test_a_rotated_token_stays_in_its_family(harness: Harness) -> None:
    first = await harness.logged_in()
    second = await harness.service.refresh(first.refresh_token)
    third = await harness.service.refresh(second.refresh_token)

    records = [harness.record_of(pair) for pair in (first, second, third)]
    assert len({record.family_id for record in records}) == 1
    assert len({record.family_expires_at for record in records}) == 1


async def test_the_rotated_token_can_keep_refreshing(harness: Harness) -> None:
    pair = await harness.logged_in()
    for _ in range(3):
        harness.clock.advance(seconds=60)
        pair = await harness.service.refresh(pair.refresh_token)

    assert pair.refresh_token


async def test_refresh_reads_the_current_role_from_the_user(harness: Harness) -> None:
    pair = await harness.logged_in()
    user = next(iter(harness.store.users.values()))
    harness.store.users[user.id] = type(user)(
        user.id, user.email, user.password_hash, Role.ADMIN, user.created_at
    )

    refreshed = await harness.service.refresh(pair.refresh_token)

    claims = jwt.decode(refreshed.access.value, options={"verify_signature": False})
    assert claims["role"] == "admin"


async def test_an_unknown_refresh_token_is_rejected(harness: Harness) -> None:
    with pytest.raises(InvalidRefreshTokenError):
        await harness.service.refresh("never-issued")


async def test_replaying_a_rotated_token_within_the_grace_window_is_rejected_without_revoking(
    harness: Harness,
) -> None:
    first = await harness.logged_in()
    second = await harness.service.refresh(first.refresh_token)
    harness.clock.advance(seconds=REUSE_GRACE.total_seconds() - 1)

    with pytest.raises(InvalidRefreshTokenError):
        await harness.service.refresh(first.refresh_token)

    assert not harness.family_revoked(second.refresh_token)
    assert (await harness.service.refresh(second.refresh_token)).refresh_token


async def test_the_grace_window_includes_exactly_ten_seconds(harness: Harness) -> None:
    first = await harness.logged_in()
    second = await harness.service.refresh(first.refresh_token)
    harness.clock.advance(seconds=10)

    with pytest.raises(InvalidRefreshTokenError):
        await harness.service.refresh(first.refresh_token)

    assert not harness.family_revoked(second.refresh_token)


async def test_replaying_a_rotated_token_after_the_grace_window_revokes_the_family(
    harness: Harness,
) -> None:
    first = await harness.logged_in()
    second = await harness.service.refresh(first.refresh_token)
    third = await harness.service.refresh(second.refresh_token)
    harness.clock.advance(seconds=11)

    with pytest.raises(InvalidRefreshTokenError):
        await harness.service.refresh(first.refresh_token)

    assert harness.family_revoked(third.refresh_token)
    with pytest.raises(InvalidRefreshTokenError):
        await harness.service.refresh(third.refresh_token)


async def test_reuse_detection_does_not_touch_other_sessions_of_the_same_user(
    harness: Harness,
) -> None:
    first = await harness.logged_in()
    other_device = await harness.service.login(EMAIL, STRONG_PASSWORD)
    await harness.service.refresh(first.refresh_token)
    harness.clock.advance(seconds=11)

    with pytest.raises(InvalidRefreshTokenError):
        await harness.service.refresh(first.refresh_token)

    assert not harness.family_revoked(other_device.refresh_token)
    assert (await harness.service.refresh(other_device.refresh_token)).refresh_token


async def test_a_zero_grace_policy_makes_reuse_strict(harness: Harness) -> None:
    key = new_signing_key()
    service = AuthService(
        harness.unit_of_work,
        harness.hasher,
        JwtAccessTokenIssuer(KeyStore([key], key.kid), ISSUER, AUDIENCE, timedelta(minutes=15)),
        harness.clock,
        RefreshPolicy(reuse_grace=timedelta(0)),
    )
    first = await harness.logged_in()
    second = await service.refresh(first.refresh_token)
    harness.clock.advance(seconds=1)

    with pytest.raises(InvalidRefreshTokenError):
        await service.refresh(first.refresh_token)

    assert harness.family_revoked(second.refresh_token)


async def test_an_expired_refresh_token_is_rejected(harness: Harness) -> None:
    pair = await harness.logged_in()
    harness.clock.advance(days=7, seconds=1)

    with pytest.raises(InvalidRefreshTokenError):
        await harness.service.refresh(pair.refresh_token)


async def test_a_session_that_keeps_refreshing_still_ends_with_its_family(
    harness: Harness,
) -> None:
    pair = await harness.logged_in()
    for _ in range(5):
        harness.clock.advance(days=5)
        pair = await harness.service.refresh(pair.refresh_token)

    harness.clock.advance(days=5)

    with pytest.raises(InvalidRefreshTokenError):
        await harness.service.refresh(pair.refresh_token)


async def test_a_rotated_token_never_outlives_its_family(harness: Harness) -> None:
    pair = await harness.logged_in()
    for _ in range(5):
        harness.clock.advance(days=5)
        pair = await harness.service.refresh(pair.refresh_token)

    record = harness.record_of(pair)
    assert record.expires_at == record.family_expires_at


async def test_refresh_fails_when_the_user_no_longer_exists(harness: Harness) -> None:
    pair = await harness.logged_in()
    harness.store.users.clear()

    with pytest.raises(InvalidRefreshTokenError):
        await harness.service.refresh(pair.refresh_token)


async def test_logout_revokes_the_whole_family(harness: Harness) -> None:
    first = await harness.logged_in()
    second = await harness.service.refresh(first.refresh_token)

    await harness.service.logout(second.refresh_token)

    assert harness.family_revoked(first.refresh_token)
    with pytest.raises(InvalidRefreshTokenError):
        await harness.service.refresh(second.refresh_token)


async def test_logout_is_idempotent(harness: Harness) -> None:
    pair = await harness.logged_in()

    await harness.service.logout(pair.refresh_token)
    await harness.service.logout(pair.refresh_token)


async def test_logout_with_an_unknown_token_succeeds_silently(harness: Harness) -> None:
    await harness.service.logout("never-issued")


async def test_logout_keeps_other_sessions_alive(harness: Harness) -> None:
    first = await harness.logged_in()
    other_device = await harness.service.login(EMAIL, STRONG_PASSWORD)

    await harness.service.logout(first.refresh_token)

    assert (await harness.service.refresh(other_device.refresh_token)).refresh_token
