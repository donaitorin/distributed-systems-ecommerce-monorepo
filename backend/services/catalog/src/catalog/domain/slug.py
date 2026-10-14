import re
import unicodedata

from catalog.domain.errors import ValidationFailedError, Violation

CATEGORY_NAME_MAX_LENGTH = 100
SLUG_MAX_LENGTH = 120

_NON_ALPHANUMERIC = re.compile(r"[^a-z0-9]+")
_WHITESPACE = re.compile(r"\s+")


def slugify(name: str) -> str:
    folded = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    return _NON_ALPHANUMERIC.sub("-", folded.lower()).strip("-")


def normalize_category_name(raw: str) -> str:
    return _WHITESPACE.sub(" ", raw).strip()


def build_category(raw_name: str) -> tuple[str, str]:
    name = normalize_category_name(raw_name)
    if not name:
        raise ValidationFailedError([Violation("name", "must not be empty", "required")])
    if len(name) > CATEGORY_NAME_MAX_LENGTH:
        raise ValidationFailedError(
            [
                Violation(
                    "name", f"must be at most {CATEGORY_NAME_MAX_LENGTH} characters", "too_long"
                )
            ]
        )
    slug = slugify(name)
    if not slug or len(slug) > SLUG_MAX_LENGTH:
        raise ValidationFailedError(
            [Violation("name", "must contain letters or digits", "invalid_name")]
        )
    return name, slug
