from fastapi import APIRouter, status

from catalog.api.dependencies import CategoryServiceDep
from catalog.api.responses import problem_responses
from catalog.api.schemas import CategoryCreate, CategoryOut
from ecommerce_auth import AdminUser

router = APIRouter(prefix="/api/v1/categories", tags=["categories"])


@router.get("", response_model=list[CategoryOut], summary="List all categories")
async def list_categories(service: CategoryServiceDep) -> list[CategoryOut]:
    return [CategoryOut.from_domain(item) for item in await service.list_all()]


@router.post(
    "",
    response_model=CategoryOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a category (admin)",
    responses=problem_responses(401, 403, 409, 422),
)
async def create_category(
    body: CategoryCreate, _admin: AdminUser, service: CategoryServiceDep
) -> CategoryOut:
    return CategoryOut.from_domain(await service.create(body.name))
