from typing import Final

from pydantic import ValidationError

MAX_VIOLATIONS: Final = 5
MAX_LOCATION_PARTS: Final = 6


class InvalidEventError(ValueError):
    pass


def describe_error(error: BaseException) -> str:
    if isinstance(error, InvalidEventError):
        return str(error)
    if isinstance(error, ValidationError):
        return describe_validation_error(error)
    return f"{type(error).__name__} raised while handling the event"


def describe_validation_error(error: ValidationError) -> str:
    violations = error.errors(include_url=False, include_context=False, include_input=False)
    shown = [
        f"{_location(violation['loc'])}: {violation['type']}"
        for violation in violations[:MAX_VIOLATIONS]
    ]
    hidden = len(violations) - len(shown)
    suffix = f" (+{hidden} more)" if hidden > 0 else ""
    return f"{len(violations)} validation errors: {'; '.join(shown)}{suffix}"


def _location(parts: tuple[int | str, ...]) -> str:
    return ".".join(str(part) for part in parts[:MAX_LOCATION_PARTS]) or "<root>"
