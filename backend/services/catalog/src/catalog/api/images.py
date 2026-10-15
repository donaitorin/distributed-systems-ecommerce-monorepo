from typing import Annotated

from fastapi import APIRouter, Path, Request, Response

from catalog.api.dependencies import IfMatch, ImageServiceDep, MediaUrlsDep
from catalog.api.products import ETAG_HEADERS, with_etag
from catalog.api.responses import problem_responses
from catalog.api.schemas import ProductOut
from catalog.api.uploads import read_image_upload
from ecommerce_auth import AdminUser

router = APIRouter(prefix="/api/v1/products", tags=["product images"])

SkuPath = Annotated[str, Path(description="Product SKU, case insensitive")]

MULTIPART_BODY = {
    "required": True,
    "content": {
        "multipart/form-data": {
            "schema": {
                "type": "object",
                "required": ["file"],
                "properties": {"file": {"type": "string", "format": "binary"}},
            }
        }
    },
}


@router.put(
    "/{sku}/image",
    response_model=ProductOut,
    summary="Set the product image (admin, requires If-Match)",
    description=(
        "Multipart field `file`: a JPEG, PNG or WebP image of at most 5 MB and 25 megapixels, "
        "validated by content. It is converted to WebP renditions of 400 px (`thumbnail_url`) "
        "and 1200 px (`image_url`) on the longest side, with metadata removed, and the product "
        "version is incremented."
    ),
    openapi_extra={"requestBody": MULTIPART_BODY},
    responses={
        200: {"headers": ETAG_HEADERS},
        **problem_responses(401, 403, 404, 412, 413, 415, 422, 428, 503),
    },
)
async def replace_image(
    sku: SkuPath,
    request: Request,
    response: Response,
    _admin: AdminUser,
    precondition: IfMatch,
    service: ImageServiceDep,
    media: MediaUrlsDep,
) -> ProductOut:
    await service.verify(sku, precondition)
    data = await read_image_upload(request)
    product = await service.replace(sku, data, precondition)
    return with_etag(response, product, media)


@router.delete(
    "/{sku}/image",
    response_model=ProductOut,
    summary="Remove the product image (admin, requires If-Match)",
    responses={
        200: {"headers": ETAG_HEADERS},
        **problem_responses(401, 403, 404, 412, 428, 503),
    },
)
async def remove_image(
    sku: SkuPath,
    response: Response,
    _admin: AdminUser,
    precondition: IfMatch,
    service: ImageServiceDep,
    media: MediaUrlsDep,
) -> ProductOut:
    product = await service.remove(sku, precondition)
    return with_etag(response, product, media)
