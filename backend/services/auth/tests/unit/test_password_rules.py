import pytest

from auth.domain.errors import ValidationFailedError
from auth.domain.password import (
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_LENGTH,
    normalize_password,
    password_violations,
)
from auth.domain.user import build_credentials

EMAIL = "ada@example.com"


def codes(password: str, email: str = EMAIL) -> list[str]:
    return [item.code for item in password_violations(password, email)]


def test_a_passphrase_of_the_minimum_length_is_accepted() -> None:
    assert codes("x" * (PASSWORD_MIN_LENGTH - 1) + "y") == []


def test_there_are_no_composition_rules() -> None:
    assert codes("alllowercaseletters") == []


def test_spaces_and_unicode_are_allowed() -> None:
    assert codes("correct horse battery staple ünï") == []


def test_too_short_is_rejected() -> None:
    assert codes("x" * (PASSWORD_MIN_LENGTH - 1)) == ["too_short"]


def test_too_long_is_rejected() -> None:
    assert codes("x1" * PASSWORD_MAX_LENGTH) == ["too_long"]


def test_the_maximum_length_is_accepted() -> None:
    assert codes(("ab" * PASSWORD_MAX_LENGTH)[:PASSWORD_MAX_LENGTH]) == []


@pytest.mark.parametrize("password", ["password123", "PASSWORD123", "1234567890", "Qwertyuiop"])
def test_common_passwords_are_rejected_ignoring_case(password: str) -> None:
    assert codes(password) == ["too_common"]


def test_a_single_repeated_character_is_rejected() -> None:
    assert codes("zzzzzzzzzzzz") == ["too_common"]


@pytest.mark.parametrize("password", ["ada@example.com", "ADA@example.com"])
def test_the_email_is_not_a_valid_password(password: str) -> None:
    assert codes(password) == ["same_as_email"]


def test_the_email_local_part_is_not_a_valid_password() -> None:
    assert codes("adalovelace", "adalovelace@example.com") == ["same_as_email"]


def test_violations_are_reported_on_the_password_field() -> None:
    assert {item.location for item in password_violations("short", EMAIL)} == {"password"}


def test_normalization_composes_unicode_without_trimming() -> None:
    assert normalize_password("  é  ") == "  é  "


def test_credentials_collect_email_and_password_violations_together() -> None:
    with pytest.raises(ValidationFailedError) as raised:
        build_credentials("not-an-email", "short")

    assert {item.location for item in raised.value.violations} == {"email", "password"}


def test_credentials_are_normalized() -> None:
    credentials = build_credentials("  Ada@Example.com ", "correct horse battery")

    assert credentials.email == "ada@example.com"
    assert credentials.password == "correct horse battery"
