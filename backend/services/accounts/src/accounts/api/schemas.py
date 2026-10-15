import re
from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    Field,
    StringConstraints,
    field_validator,
)

from accounts.application.accounts import ProfilePage
from accounts.domain.profile import Address, NewAddress, Profile, ProfileChanges

PHONE_SEPARATORS = re.compile(r"[ \-.()]")
PHONE_PATTERN = re.compile(r"\+\d{8,15}")
COUNTRY_PATTERN = re.compile(r"[A-Z]{2}")
PAGE_SIZES = (25, 50, 100)


def normalize_phone(value: object) -> object:
    if not isinstance(value, str):
        return value
    return PHONE_SEPARATORS.sub("", value.strip())


def check_phone(value: str) -> str:
    if not PHONE_PATTERN.fullmatch(value):
        raise ValueError("phone must start with + and have 8 to 15 digits")
    return value


def upper_country(value: object) -> object:
    return value.strip().upper() if isinstance(value, str) else value


def check_country(value: str) -> str:
    if not COUNTRY_PATTERN.fullmatch(value):
        raise ValueError("country must be an ISO 3166-1 alpha-2 code")
    return value


def require_page_size(value: int) -> int:
    if value not in PAGE_SIZES:
        raise ValueError("limit must be 25, 50 or 100")
    return value


def blank_to_none(value: object) -> object:
    if isinstance(value, str) and not value.strip():
        return None
    return value


def trimmed(max_length: int) -> StringConstraints:
    return StringConstraints(strip_whitespace=True, min_length=1, max_length=max_length)


PageSize = Annotated[int, AfterValidator(require_page_size)]
NameField = Annotated[str, trimmed(100)]
PhoneField = Annotated[str, BeforeValidator(normalize_phone), AfterValidator(check_phone)]
CountryField = Annotated[str, BeforeValidator(upper_country), AfterValidator(check_country)]


class ProfilePatchIn(BaseModel):
    name: NameField | None = Field(default=None, examples=["Ada Lovelace"])
    phone: Annotated[PhoneField | None, BeforeValidator(blank_to_none)] = Field(
        default=None, examples=["+34600111222"]
    )

    @field_validator("name", mode="before")
    @classmethod
    def reject_null_name(cls, value: object) -> object:
        if value is None:
            raise ValueError("name cannot be cleared")
        return value

    def to_changes(self) -> ProfileChanges:
        return ProfileChanges(
            name=self.name, phone=self.phone, change_phone="phone" in self.model_fields_set
        )


class AddressIn(BaseModel):
    recipient_name: NameField
    line1: Annotated[str, trimmed(200)]
    line2: Annotated[Annotated[str, trimmed(200)] | None, BeforeValidator(blank_to_none)] = None
    city: Annotated[str, trimmed(100)]
    region: Annotated[Annotated[str, trimmed(100)] | None, BeforeValidator(blank_to_none)] = None
    postal_code: Annotated[str, trimmed(20)]
    country: CountryField = Field(examples=["ES"])
    phone: Annotated[PhoneField | None, BeforeValidator(blank_to_none)] = None

    def to_domain(self) -> NewAddress:
        return NewAddress(**self.model_dump())


class ProfileOut(BaseModel):
    user_id: UUID
    email: str | None
    role: str
    name: str | None
    phone: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, profile: Profile) -> "ProfileOut":
        return cls(
            user_id=profile.user_id,
            email=profile.email,
            role=profile.role,
            name=profile.name,
            phone=profile.phone,
            created_at=profile.created_at,
            updated_at=profile.updated_at,
        )


class ProfilePageOut(BaseModel):
    items: list[ProfileOut]
    next_cursor: str | None

    @classmethod
    def from_domain(cls, page: ProfilePage) -> "ProfilePageOut":
        return cls(
            items=[ProfileOut.from_domain(item) for item in page.items],
            next_cursor=page.next_cursor,
        )


class AddressOut(BaseModel):
    id: UUID
    recipient_name: str
    line1: str
    line2: str | None
    city: str
    region: str | None
    postal_code: str
    country: str
    phone: str | None
    created_at: datetime

    @classmethod
    def from_domain(cls, address: Address) -> "AddressOut":
        return cls(
            id=address.id,
            recipient_name=address.recipient_name,
            line1=address.line1,
            line2=address.line2,
            city=address.city,
            region=address.region,
            postal_code=address.postal_code,
            country=address.country,
            phone=address.phone,
            created_at=address.created_at,
        )


class AddressListOut(BaseModel):
    items: list[AddressOut]


class FieldProblem(BaseModel):
    location: str
    message: str
    type: str


class ProblemOut(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str
    request_id: str | None = None
    errors: list[FieldProblem] | None = None
