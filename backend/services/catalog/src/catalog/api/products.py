from typing import Annotated

from fastapi import APIRouter, Path, Query, Response, status

from catalog.api.dependencies import IfMatch, ProductServiceDep
from catalog.api.responses import problem_responses
from catalog.api.schemas import ProblemOut, ProductCreate, ProductOut, ProductPage, ProductWrite
from catalog.domain.preconditions import format_entity_tag
from catalog.domain.product import Product
from ecommerce_auth import AdminUser

router = APIRouter(prefix="/api/v1/products", tags=["products"])

SkuPath = Annotated[str, Path(description="Product SKU, case insensitive")]
ETAG_HEADERS = {"ETag": {"description": "Version of the product", "schema": {"type": "string"}}}


def with_etag(response: Response, product: Product) -> ProductOut:
    response.headers["ETag"] = format_entity_tag(product.version)
    return ProductOut.from_domain(product)


@router.get("", response_model=ProductPage, summary="List products")
async def list_products(
    service: ProductServiceDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ProductPage:
    products = await service.list(limit)
    return ProductPage(items=[ProductOut.from_domain(item) for item in products])


@router.get(
    "/{sku}",
    response_model=ProductOut,
    summary="Get a product",
    responses={
        200: {"headers": ETAG_HEADERS},
        404: {"model": ProblemOut, "description": "Unknown or deleted SKU"},
    },
)
async def get_product(sku: SkuPath, response: Response, service: ProductServiceDep) -> ProductOut:
    return with_etag(response, await service.get(sku))


@router.post(
    "",
    response_model=ProductOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a product (admin)",
    responses={
        201: {"headers": ETAG_HEADERS},
        **problem_responses(401, 403, 409, 422),
    },
)
async def create_product(
    body: ProductCreate,
    response: Response,
    _admin: AdminUser,
    service: ProductServiceDep,
) -> ProductOut:
    product = await service.create(
        sku=body.sku,
        name=body.name,
        description=body.description,
        category_id=body.category_id,
        price=body.price,
        stock=body.stock,
        weight_kg=body.weight_kg,
    )
    response.headers["Location"] = f"/api/v1/products/{product.sku}"
    return with_etag(response, product)


@router.put(
    "/{sku}",
    response_model=ProductOut,
    summary="Replace a product (admin, requires If-Match)",
    responses={
        200: {"headers": ETAG_HEADERS},
        **problem_responses(401, 403, 404, 412, 422, 428),
    },
)
async def replace_product(
    sku: SkuPath,
    body: ProductWrite,
    response: Response,
    _admin: AdminUser,
    precondition: IfMatch,
    service: ProductServiceDep,
) -> ProductOut:
    product = await service.replace(
        sku=sku,
        name=body.name,
        description=body.description,
        category_id=body.category_id,
        price=body.price,
        stock=body.stock,
        weight_kg=body.weight_kg,
        precondition=precondition,
    )
    return with_etag(response, product)


@router.delete(
    "/{sku}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft delete a product (admin, requires If-Match)",
    responses=problem_responses(401, 403, 404, 412, 428),
)
async def delete_product(
    sku: SkuPath,
    _admin: AdminUser,
    precondition: IfMatch,
    service: ProductServiceDep,
) -> Response:
    await service.delete(sku, precondition)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
