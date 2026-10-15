import unicodedata

from auth.domain.errors import Violation

EMAIL_MAX_LENGTH = 254
LOCAL_PART_MAX_LENGTH = 64


def normalize_email(raw: str) -> str:
    return unicodedata.normalize("NFKC", raw).strip().lower()


def email_violations(normalized: str) -> list[Violation]:
    reason = _invalid_reason(normalized)
    if reason is None:
        return []
    return [Violation("email", reason, "invalid_email")]


def _invalid_reason(email: str) -> str | None:
    if not email:
        return "must not be empty"
    if len(email) > EMAIL_MAX_LENGTH:
        return f"must be at most {EMAIL_MAX_LENGTH} characters"
    if any(character.isspace() or unicodedata.category(character) == "Cc" for character in email):
        return "must not contain whitespace or control characters"
    if email.count("@") != 1:
        return "must contain exactly one @"
    local, domain = email.split("@")
    if not local or len(local) > LOCAL_PART_MAX_LENGTH:
        return f"the part before @ must have 1 to {LOCAL_PART_MAX_LENGTH} characters"
    if "." not in domain or domain.startswith(".") or domain.endswith(".") or ".." in domain:
        return "the part after @ must be a domain such as example.com"
    return None
