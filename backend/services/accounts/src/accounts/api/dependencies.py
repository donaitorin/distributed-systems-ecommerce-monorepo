from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request

from accounts.application.accounts import AccountService, Identity
from ecommerce_auth import AuthenticatedUser, CustomerUser, InvalidTokenError


def get_account_service(request: Request) -> AccountService:
    service: AccountService = request.app.state.account_service
    return service


def get_identity(user: CustomerUser) -> Identity:
    return identity_of(user)


def identity_of(user: AuthenticatedUser) -> Identity:
    try:
        user_id = UUID(user.user_id)
    except ValueError as error:
        raise InvalidTokenError("The access token is invalid or expired") from error
    return Identity(user_id, user.email, user.role.value, user.issued_at)


AccountServiceDep = Annotated[AccountService, Depends(get_account_service)]
IdentityDep = Annotated[Identity, Depends(get_identity)]
