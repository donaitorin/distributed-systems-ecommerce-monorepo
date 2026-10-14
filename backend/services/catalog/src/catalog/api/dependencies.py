from typing import Annotated

from fastapi import Depends, Header, Request

from catalog.api.errors import PreconditionRequiredError
from catalog.application.categories import CategoryService
from catalog.application.products import ProductService
from catalog.domain.preconditions import VersionPrecondition


def get_product_service(request: Request) -> ProductService:
    service: ProductService = request.app.state.product_service
    return service


def get_category_service(request: Request) -> CategoryService:
    service: CategoryService = request.app.state.category_service
    return service


def require_if_match(
    if_match: Annotated[
        str | None,
        Header(description="ETag of the version being changed, or * to match any version"),
    ] = None,
) -> VersionPrecondition:
    if if_match is None:
        raise PreconditionRequiredError
    return VersionPrecondition.parse(if_match)


ProductServiceDep = Annotated[ProductService, Depends(get_product_service)]
CategoryServiceDep = Annotated[CategoryService, Depends(get_category_service)]
IfMatch = Annotated[VersionPrecondition, Depends(require_if_match)]
