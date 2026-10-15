from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Response, status

from auth.api.dependencies import (
    AuthServiceDep,
    JwksDep,
    RegistrationServiceDep,
    RoleServiceDep,
)
from auth.api.responses import problem_responses
from auth.api.schemas import CredentialsIn, RefreshIn, RoleChangeIn, TokensOut, UserOut
from ecommerce_auth import AdminUser
from ecommerce_observability import get_request_id

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

NO_STORE = "no-store"
JWKS_CACHE_CONTROL = "public, max-age=300"


def correlation_id() -> UUID:
    current = get_request_id()
    try:
        return UUID(current) if current else uuid4()
    except ValueError:
        return uuid4()


@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a customer account",
    responses=problem_responses(409, 422),
)
async def register(body: CredentialsIn, service: RegistrationServiceDep) -> UserOut:
    return UserOut.from_domain(await service.register(body.email, body.password, correlation_id()))


@router.post(
    "/login",
    response_model=TokensOut,
    summary="Exchange credentials for an access token and a refresh token",
    responses=problem_responses(401),
)
async def login(body: CredentialsIn, service: AuthServiceDep, response: Response) -> TokensOut:
    response.headers["Cache-Control"] = NO_STORE
    return TokensOut.from_pair(await service.login(body.email, body.password))


@router.post(
    "/refresh",
    response_model=TokensOut,
    summary="Rotate a refresh token for a new token pair",
    responses=problem_responses(401),
)
async def refresh(body: RefreshIn, service: AuthServiceDep, response: Response) -> TokensOut:
    response.headers["Cache-Control"] = NO_STORE
    return TokensOut.from_pair(await service.refresh(body.refresh_token))


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke the session behind a refresh token",
)
async def logout(body: RefreshIn, service: AuthServiceDep) -> Response:
    await service.logout(body.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/.well-known/jwks.json", summary="Public signing keys")
async def jwks(document: JwksDep, response: Response) -> dict[str, Any]:
    response.headers["Cache-Control"] = JWKS_CACHE_CONTROL
    return document


@router.patch(
    "/users/{user_id}/role",
    response_model=UserOut,
    summary="Change a user's role (admin)",
    responses=problem_responses(401, 403, 404, 409, 422),
)
async def change_role(
    user_id: UUID, body: RoleChangeIn, admin: AdminUser, service: RoleServiceDep
) -> UserOut:
    user = await service.change_role(UUID(admin.user_id), user_id, body.role, correlation_id())
    return UserOut.from_domain(user)
