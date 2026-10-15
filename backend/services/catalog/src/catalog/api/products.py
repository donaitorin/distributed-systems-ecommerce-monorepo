from typing import Annotated

from fastapi import APIRouter, Depends, Path, Response, status

from catalog.api.dependencies import IfMatch, ListParams, ProductServiceDep, list_params
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


@router.get(
    "",
    response_model=ProductPage,
    summary="Search and list products",
    description=(
        "Keyset-paginated listing. Without q the default order is newest first; with q it is "
        "relevance, and typos in q still match. sort=relevance without q falls back to newest. "
        "in_stock=true hides sold-out products; in_stock=false is the same as omitting it. "
        "An unknown category slug returns an empty page. A cursor is only valid with the q, "
        "category, price, in_stock and sort values it was issued for."
    ),
    responses=problem_responses(422, 503),
)
async def list_products(
    service: ProductServiceDep,
    params: Annotated[ListParams, Depends(list_params)],
) -> ProductPage:
    listing = await service.search(params.filters, params.sort, params.limit, params.cursor)
    return ProductPage.from_domain(listing)


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
