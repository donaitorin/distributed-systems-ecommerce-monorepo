from ecommerce_auth.dependencies import (
    AdminUser,
    CurrentUser,
    CustomerUser,
    get_current_user,
    get_token_verifier,
    require_role,
)
from ecommerce_auth.errors import AuthError, ForbiddenError, InvalidTokenError, KeysUnavailableError
from ecommerce_auth.jwks import JwksClient, SigningKeyProvider
from ecommerce_auth.roles import Role
from ecommerce_auth.settings import DEFAULT_AUDIENCE, JwtSettings
from ecommerce_auth.verifier import (
    AuthenticatedUser,
    ManagedTokenVerifier,
    TokenVerifier,
    create_token_verifier,
)

__all__ = [
    "DEFAULT_AUDIENCE",
    "AdminUser",
    "AuthError",
    "AuthenticatedUser",
    "CurrentUser",
    "CustomerUser",
    "ForbiddenError",
    "InvalidTokenError",
    "JwksClient",
    "JwtSettings",
    "KeysUnavailableError",
    "ManagedTokenVerifier",
    "Role",
    "SigningKeyProvider",
    "TokenVerifier",
    "create_token_verifier",
    "get_current_user",
    "get_token_verifier",
    "require_role",
]
