from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from auth.domain.email import email_violations, normalize_email
from auth.domain.errors import ValidationFailedError
from auth.domain.password import normalize_password, password_violations


class Role(StrEnum):
    CUSTOMER = "customer"
    ADMIN = "admin"


@dataclass(frozen=True, slots=True)
class Credentials:
    email: str
    password: str


@dataclass(frozen=True, slots=True)
class User:
    id: UUID
    email: str
    password_hash: str
    role: Role
    created_at: datetime


def build_credentials(raw_email: str, raw_password: str) -> Credentials:
    email = normalize_email(raw_email)
    password = normalize_password(raw_password)
    violations = email_violations(email) + password_violations(password, email)
    if violations:
        raise ValidationFailedError(violations)
    return Credentials(email, password)
