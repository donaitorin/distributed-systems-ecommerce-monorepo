import unicodedata

from auth.domain.errors import Violation

PASSWORD_MIN_LENGTH = 10
PASSWORD_MAX_LENGTH = 128

COMMON_PASSWORDS = frozenset(
    {
        "password",
        "password1",
        "password12",
        "password123",
        "password1234",
        "passw0rd123",
        "1234567890",
        "12345678910",
        "123456789012",
        "0123456789",
        "1111111111",
        "0000000000",
        "qwertyuiop",
        "qwerty1234",
        "qwerty12345",
        "qwertyuiop123",
        "asdfghjkl",
        "asdfghjkl123",
        "1q2w3e4r5t",
        "1qaz2wsx3edc",
        "iloveyou123",
        "letmein1234",
        "welcome1234",
        "welcome123",
        "administrator",
        "admin123456",
        "changeme123",
        "abc1234567",
        "abcdefghij",
        "trustno1234",
        "monkey12345",
        "dragon12345",
        "football123",
        "baseball123",
        "superman123",
        "princess123",
        "sunshine123",
        "master12345",
        "login12345",
        "starwars123",
    }
)


def normalize_password(raw: str) -> str:
    return unicodedata.normalize("NFKC", raw)


def password_violations(password: str, email: str) -> list[Violation]:
    if len(password) < PASSWORD_MIN_LENGTH:
        return [_violation(f"must be at least {PASSWORD_MIN_LENGTH} characters", "too_short")]
    if len(password) > PASSWORD_MAX_LENGTH:
        return [_violation(f"must be at most {PASSWORD_MAX_LENGTH} characters", "too_long")]
    lowered = password.lower()
    if lowered in COMMON_PASSWORDS:
        return [_violation("is too common", "too_common")]
    if lowered in {email, email.split("@")[0]}:
        return [_violation("must not be the same as the email", "same_as_email")]
    if len(set(password)) == 1:
        return [_violation("must not repeat a single character", "too_common")]
    return []


def _violation(message: str, code: str) -> Violation:
    return Violation("password", message, code)
