from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ecommerce_auth.errors import ForbiddenError, InvalidTokenError
from ecommerce_auth.roles import Role
from ecommerce_auth.verifier import AuthenticatedUser, TokenVerifier

_bearer = HTTPBearer(auto_error=False)


def get_token_verifier(request: Request) -> TokenVerifier:
    verifier: TokenVerifier | None = getattr(request.app.state, "token_verifier", None)
    if verifier is None:
        raise RuntimeError("token verifier is not configured on the application")
    return verifier


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    verifier: Annotated[TokenVerifier, Depends(get_token_verifier)],
) -> AuthenticatedUser:
    if credentials is None:
        raise InvalidTokenError("A bearer access token is required")
    return await verifier.verify(credentials.credentials)


def require_role(*allowed: Role) -> Callable[[AuthenticatedUser], Awaitable[AuthenticatedUser]]:
    async def dependency(
        user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    ) -> AuthenticatedUser:
        if user.role not in allowed:
            raise ForbiddenError("The current role cannot perform this action")
        return user

    return dependency


CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
CustomerUser = Annotated[AuthenticatedUser, Depends(require_role(Role.CUSTOMER, Role.ADMIN))]
AdminUser = Annotated[AuthenticatedUser, Depends(require_role(Role.ADMIN))]
