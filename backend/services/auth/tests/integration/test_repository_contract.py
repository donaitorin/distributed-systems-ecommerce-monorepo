from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from auth.application.errors import EmailTakenError
from auth.application.ports import UnitOfWorkFactory
from auth.domain.user import Role

NOW = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)


def unique_email() -> str:
    return f"user-{uuid4().hex[:12]}@example.com"


async def add_user(unit_of_work: UnitOfWorkFactory, role: Role = Role.CUSTOMER) -> tuple[str, str]:
    email = unique_email()
    async with unit_of_work() as uow:
        user = await uow.users.add(email, "hash", role, NOW)
        await uow.commit()
    return email, str(user.id)


async def test_added_users_can_be_read_back_by_email_and_id(
    unit_of_work: UnitOfWorkFactory,
) -> None:
    email, user_id = await add_user(unit_of_work, Role.ADMIN)

    async with unit_of_work() as uow:
        by_email = await uow.users.get_by_email(email)
        assert by_email is not None
        by_id = await uow.users.get(by_email.id)

    assert by_id == by_email
    assert str(by_email.id) == user_id
    assert by_email.role is Role.ADMIN
    assert by_email.password_hash == "hash"
    assert by_email.created_at == NOW


async def test_unknown_users_are_none(unit_of_work: UnitOfWorkFactory) -> None:
    async with unit_of_work() as uow:
        assert await uow.users.get_by_email("nobody@example.com") is None
        assert await uow.users.get(uuid4()) is None


async def test_a_duplicate_email_is_reported_as_taken(unit_of_work: UnitOfWorkFactory) -> None:
    email, _ = await add_user(unit_of_work)

    async with unit_of_work() as uow:
        with pytest.raises(EmailTakenError):
            await uow.users.add(email, "other", Role.CUSTOMER, NOW)


async def test_the_password_hash_can_be_replaced(unit_of_work: UnitOfWorkFactory) -> None:
    email, _ = await add_user(unit_of_work)
    async with unit_of_work() as uow:
        user = await uow.users.get_by_email(email)
        assert user is not None
        await uow.users.update_password_hash(user.id, "upgraded", NOW + timedelta(hours=1))
        await uow.commit()

    async with unit_of_work() as uow:
        again = await uow.users.get_by_email(email)

    assert again is not None
    assert again.password_hash == "upgraded"


async def issue_token(
    unit_of_work: UnitOfWorkFactory, user_email: str, family_id: UUID, token_hash: str
) -> None:
    async with unit_of_work() as uow:
        user = await uow.users.get_by_email(user_email)
        assert user is not None
        await uow.refresh_tokens.add(
            token_hash=token_hash,
            family_id=family_id,
            user_id=user.id,
            expires_at=NOW + timedelta(days=7),
            family_expires_at=NOW + timedelta(days=30),
            now=NOW,
        )
        await uow.commit()


def unique_hash() -> str:
    return uuid4().hex + uuid4().hex


async def test_a_stored_refresh_token_is_found_by_its_hash(unit_of_work: UnitOfWorkFactory) -> None:
    email, user_id = await add_user(unit_of_work)
    family_id, token_hash = uuid4(), unique_hash()
    await issue_token(unit_of_work, email, family_id, token_hash)

    async with unit_of_work() as uow:
        record = await uow.refresh_tokens.get_for_update(token_hash)

    assert record is not None
    assert record.family_id == family_id
    assert str(record.user_id) == user_id
    assert record.expires_at == NOW + timedelta(days=7)
    assert record.family_expires_at == NOW + timedelta(days=30)
    assert record.used_at is None
    assert record.revoked_at is None


async def test_an_unknown_hash_is_none(unit_of_work: UnitOfWorkFactory) -> None:
    async with unit_of_work() as uow:
        assert await uow.refresh_tokens.get_for_update(unique_hash()) is None


async def test_marking_a_token_used_records_when(unit_of_work: UnitOfWorkFactory) -> None:
    email, _ = await add_user(unit_of_work)
    token_hash = unique_hash()
    await issue_token(unit_of_work, email, uuid4(), token_hash)
    async with unit_of_work() as uow:
        record = await uow.refresh_tokens.get_for_update(token_hash)
        assert record is not None
        await uow.refresh_tokens.mark_used(record.id, NOW + timedelta(minutes=1))
        await uow.commit()

    async with unit_of_work() as uow:
        again = await uow.refresh_tokens.get_for_update(token_hash)

    assert again is not None
    assert again.used_at == NOW + timedelta(minutes=1)


async def test_revoking_a_family_revokes_every_member_and_only_that_family(
    unit_of_work: UnitOfWorkFactory,
) -> None:
    email, _ = await add_user(unit_of_work)
    family, other_family = uuid4(), uuid4()
    members = [unique_hash(), unique_hash()]
    bystander = unique_hash()
    for token_hash in members:
        await issue_token(unit_of_work, email, family, token_hash)
    await issue_token(unit_of_work, email, other_family, bystander)

    async with unit_of_work() as uow:
        await uow.refresh_tokens.revoke_family(family, NOW + timedelta(minutes=2))
        await uow.commit()

    async with unit_of_work() as uow:
        revoked = [await uow.refresh_tokens.get_for_update(item) for item in members]
        untouched = await uow.refresh_tokens.get_for_update(bystander)
    assert all(
        item is not None and item.revoked_at == NOW + timedelta(minutes=2) for item in revoked
    )
    assert untouched is not None
    assert untouched.revoked_at is None


async def test_revoking_twice_keeps_the_first_revocation_time(
    unit_of_work: UnitOfWorkFactory,
) -> None:
    email, _ = await add_user(unit_of_work)
    family, token_hash = uuid4(), unique_hash()
    await issue_token(unit_of_work, email, family, token_hash)
    for minutes in (1, 5):
        async with unit_of_work() as uow:
            await uow.refresh_tokens.revoke_family(family, NOW + timedelta(minutes=minutes))
            await uow.commit()

    async with unit_of_work() as uow:
        record = await uow.refresh_tokens.get_for_update(token_hash)

    assert record is not None
    assert record.revoked_at == NOW + timedelta(minutes=1)
