from typing import Any

from fastapi import APIRouter, Response, status

from auth.api.dependencies import AuthServiceDep, JwksDep, RegistrationServiceDep
from auth.api.responses import problem_responses
from auth.api.schemas import CredentialsIn, RefreshIn, TokensOut, UserOut

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

NO_STORE = "no-store"
JWKS_CACHE_CONTROL = "public, max-age=300"


@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a customer account",
    responses=problem_responses(409, 422),
)
async def register(body: CredentialsIn, service: RegistrationServiceDep) -> UserOut:
    return UserOut.from_domain(await service.register(body.email, body.password))


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
