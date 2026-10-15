from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field

from auth.application.ports import AccessToken
from auth.application.service import TokenPair
from auth.domain.user import Role, User

CREDENTIAL_MAX_INPUT = 1024
TOKEN_MAX_INPUT = 512

EmailField = Annotated[str, Field(max_length=CREDENTIAL_MAX_INPUT, examples=["ada@example.com"])]
PasswordField = Annotated[str, Field(max_length=CREDENTIAL_MAX_INPUT)]


class CredentialsIn(BaseModel):
    email: EmailField
    password: PasswordField


class RefreshIn(BaseModel):
    refresh_token: Annotated[str, Field(max_length=TOKEN_MAX_INPUT)]


class UserOut(BaseModel):
    id: UUID
    email: str
    role: Role

    @classmethod
    def from_domain(cls, user: User) -> "UserOut":
        return cls(id=user.id, email=user.email, role=user.role)


class TokensOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int = Field(description="Access token lifetime in seconds")

    @classmethod
    def from_pair(cls, pair: TokenPair) -> "TokensOut":
        access: AccessToken = pair.access
        return cls(
            access_token=access.value,
            refresh_token=pair.refresh_token,
            expires_in=access.expires_in,
        )


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
