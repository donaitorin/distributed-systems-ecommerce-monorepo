from collections.abc import Callable
from pathlib import Path

import pytest
from auth_testing.support import STRONG_PASSWORD, FakeHasher

from auth.domain.errors import ValidationFailedError
from auth.domain.user import Role
from auth.infra.keys import generate_key_file
from auth.infra.memory import InMemoryStore, InMemoryUnitOfWork
from auth.tools import keys as keys_tool
from auth.tools.seed import run, seed_admin


def unit_of_work_for(store: InMemoryStore) -> Callable[[], InMemoryUnitOfWork]:
    return lambda: InMemoryUnitOfWork(store)


async def test_the_seed_creates_the_admin() -> None:
    store = InMemoryStore()

    created = await seed_admin(
        lambda: InMemoryUnitOfWork(store), FakeHasher(), "Admin@Example.com", STRONG_PASSWORD
    )

    assert created is True
    (admin,) = store.users.values()
    assert admin.email == "admin@example.com"
    assert admin.role is Role.ADMIN


async def test_running_the_seed_twice_changes_nothing() -> None:
    store = InMemoryStore()
    work = unit_of_work_for(store)
    await seed_admin(work, FakeHasher(), "admin@example.com", STRONG_PASSWORD)
    (before,) = store.users.values()

    created = await seed_admin(work, FakeHasher(), "admin@example.com", "another long passphrase")

    assert created is False
    assert list(store.users.values()) == [before]


async def test_the_seed_never_demotes_or_resets_an_existing_account() -> None:
    store = InMemoryStore()
    work = unit_of_work_for(store)
    await seed_admin(work, FakeHasher(), "admin@example.com", STRONG_PASSWORD)
    (admin,) = store.users.values()

    await seed_admin(work, FakeHasher(), "admin@example.com", "another long passphrase")

    assert store.users[admin.id].password_hash == admin.password_hash
    assert store.users[admin.id].role is Role.ADMIN


async def test_the_seed_refuses_a_weak_password() -> None:
    with pytest.raises(ValidationFailedError):
        await seed_admin(
            lambda: InMemoryUnitOfWork(InMemoryStore()), FakeHasher(), "admin@example.com", "admin"
        )


@pytest.mark.parametrize(
    "environ",
    [{}, {"AUTH_ADMIN_EMAIL": "admin@example.com"}, {"AUTH_ADMIN_PASSWORD": STRONG_PASSWORD}],
)
async def test_the_seed_is_skipped_unless_both_variables_are_set(environ: dict[str, str]) -> None:
    assert await run(environ) is None


def test_keys_tool_generates_and_lists(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert keys_tool.run(["--keys-dir", str(tmp_path), "generate"]) == 0
    generated = capsys.readouterr().out.strip()

    assert keys_tool.run(["--keys-dir", str(tmp_path), "list"]) == 0

    assert capsys.readouterr().out.strip() == f"{generated} (active)"


def test_keys_tool_marks_only_the_active_key(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    first = generate_key_file(tmp_path)
    second = generate_key_file(tmp_path)
    monkeypatch.setenv("AUTH_ACTIVE_KID", first.kid)

    keys_tool.run(["--keys-dir", str(tmp_path), "list"])

    lines = capsys.readouterr().out.strip().splitlines()
    assert f"{first.kid} (active)" in lines
    assert second.kid in lines
