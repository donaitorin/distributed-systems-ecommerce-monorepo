from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from accounts.api.dependencies import AccountServiceDep, IdentityDep
from accounts.api.responses import problem_responses
from accounts.api.schemas import (
    AddressIn,
    AddressListOut,
    AddressOut,
    PageSize,
    ProfileOut,
    ProfilePageOut,
    ProfilePatchIn,
)
from accounts.domain.listing import ProfileFilters
from ecommerce_auth import AdminUser, Role

router = APIRouter(prefix="/api/v1/accounts", tags=["accounts"])

NO_STORE = "no-store"


@router.get(
    "/me",
    response_model=ProfileOut,
    summary="Get the profile of the authenticated user",
    responses=problem_responses(401),
)
async def get_me(
    identity: IdentityDep, service: AccountServiceDep, response: Response
) -> ProfileOut:
    response.headers["Cache-Control"] = NO_STORE
    return ProfileOut.from_domain(await service.me(identity))


@router.patch(
    "/me",
    response_model=ProfileOut,
    summary="Change the name or phone of the authenticated user",
    responses=problem_responses(401, 422),
)
async def patch_me(
    body: ProfilePatchIn, identity: IdentityDep, service: AccountServiceDep, response: Response
) -> ProfileOut:
    response.headers["Cache-Control"] = NO_STORE
    return ProfileOut.from_domain(await service.update_me(identity, body.to_changes()))


@router.get(
    "/me/addresses",
    response_model=AddressListOut,
    summary="List the shipping addresses of the authenticated user",
    responses=problem_responses(401),
)
async def list_addresses(
    identity: IdentityDep, service: AccountServiceDep, response: Response
) -> AddressListOut:
    response.headers["Cache-Control"] = NO_STORE
    addresses = await service.list_addresses(identity)
    return AddressListOut(items=[AddressOut.from_domain(item) for item in addresses])


@router.post(
    "/me/addresses",
    response_model=AddressOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add a shipping address",
    responses=problem_responses(401, 409, 422),
)
async def add_address(
    body: AddressIn, identity: IdentityDep, service: AccountServiceDep
) -> AddressOut:
    return AddressOut.from_domain(await service.add_address(identity, body.to_domain()))


@router.delete(
    "/me/addresses/{address_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a shipping address",
    responses=problem_responses(401, 404, 422),
)
async def delete_address(
    address_id: UUID, identity: IdentityDep, service: AccountServiceDep
) -> Response:
    await service.delete_address(identity, address_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "",
    response_model=ProfilePageOut,
    summary="List user profiles (admin)",
    responses=problem_responses(401, 403, 422),
)
async def list_profiles(
    _admin: AdminUser,
    service: AccountServiceDep,
    email: Annotated[
        str | None, Query(max_length=254, description="Case-insensitive email prefix")
    ] = None,
    role: Annotated[Role | None, Query()] = None,
    limit: Annotated[PageSize, Query(description="Page size: 25, 50 or 100")] = 25,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
) -> ProfilePageOut:
    filters = ProfileFilters(email_prefix=email, role=role.value if role else None)
    return ProfilePageOut.from_domain(await service.list_profiles(filters, limit, cursor))
