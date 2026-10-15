import pytest

from auth.domain.email import EMAIL_MAX_LENGTH, email_violations, normalize_email


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  Ada@Example.COM ", "ada@example.com"),
        ("ADA@EXAMPLE.COM", "ada@example.com"),
        ("\uff41\uff44\uff41@example.com", "ada@example.com"),
        ("\tada@example.com\n", "ada@example.com"),
    ],
)
def test_normalization_trims_lowercases_and_folds_compatibility_forms(
    raw: str, expected: str
) -> None:
    assert normalize_email(raw) == expected


@pytest.mark.parametrize(
    "email",
    ["ada@example.com", "ada+tag@mail.example.co.uk", "a@b.c", "ünï@exämple.com"],
)
def test_structurally_valid_emails_have_no_violations(email: str) -> None:
    assert email_violations(email) == []


@pytest.mark.parametrize(
    ("email", "fragment"),
    [
        ("", "empty"),
        ("ada", "exactly one @"),
        ("ada@@example.com", "exactly one @"),
        ("a@b@example.com", "exactly one @"),
        ("@example.com", "before @"),
        ("a" * 65 + "@example.com", "before @"),
        ("ada@localhost", "domain"),
        ("ada@.example.com", "domain"),
        ("ada@example.com.", "domain"),
        ("ada@exa..mple.com", "domain"),
        ("ada lovelace@example.com", "whitespace"),
        ("ada\x00@example.com", "control"),
        ("a@" + "b" * EMAIL_MAX_LENGTH + ".com", "at most"),
    ],
)
def test_structurally_invalid_emails_are_reported_on_the_email_field(
    email: str, fragment: str
) -> None:
    violations = email_violations(email)

    assert len(violations) == 1
    assert violations[0].location == "email"
    assert violations[0].code == "invalid_email"
    assert fragment in violations[0].message
