from typing import Annotated, Any

from fastapi import Depends, Request

from auth.application.registration import RegistrationService
from auth.application.roles import RoleService
from auth.application.service import AuthService


def get_auth_service(request: Request) -> AuthService:
    service: AuthService = request.app.state.auth_service
    return service


def get_registration_service(request: Request) -> RegistrationService:
    service: RegistrationService = request.app.state.registration_service
    return service


def get_role_service(request: Request) -> RoleService:
    service: RoleService = request.app.state.role_service
    return service


def get_jwks(request: Request) -> dict[str, Any]:
    document: dict[str, Any] = request.app.state.jwks
    return document


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
RegistrationServiceDep = Annotated[RegistrationService, Depends(get_registration_service)]
RoleServiceDep = Annotated[RoleService, Depends(get_role_service)]
JwksDep = Annotated[dict[str, Any], Depends(get_jwks)]
