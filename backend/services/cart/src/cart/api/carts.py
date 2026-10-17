from typing import Annotated

from fastapi import APIRouter, Path, Response, status

from cart.api.dependencies import CartServiceDep, MediaBaseUrlDep, UserIdDep
from cart.api.responses import problem_responses
from cart.api.schemas import CartOut, ItemIn

router = APIRouter(prefix="/api/v1/cart", tags=["cart"])

NO_STORE = "no-store"
SkuPath = Annotated[str, Path(description="Product SKU, case insensitive")]


@router.get(
    "",
    response_model=CartOut,
    summary="Get the cart of the authenticated user",
    description=(
        "Lines keep the price and name saved when they were added. `flags` compares each "
        "line with what the catalog says now: `price_changed` (old and new price), "
        "`unavailable` (the product was retired) and `insufficient_stock` (`available` may "
        "be 0). Nothing is changed silently."
    ),
    responses=problem_responses(401, 503),
)
async def get_cart(
    user_id: UserIdDep, service: CartServiceDep, media: MediaBaseUrlDep, response: Response
) -> CartOut:
    response.headers["Cache-Control"] = NO_STORE
    return CartOut.from_domain(await service.view(user_id), media)


@router.put(
    "/items/{sku}",
    response_model=CartOut,
    summary="Set the quantity of a product in the cart",
    description=(
        "Creates the line or replaces its quantity (1 to 99). A new line reads the product "
        "from the catalog and saves its price and name. A cart holds at most 100 different "
        "products. With `accepted_price` the line takes the current price and name, but only "
        "if that price is the one sent."
    ),
    responses=problem_responses(401, 404, 409, 422, 503),
)
async def put_item(
    sku: SkuPath,
    body: ItemIn,
    user_id: UserIdDep,
    service: CartServiceDep,
    media: MediaBaseUrlDep,
    response: Response,
) -> CartOut:
    response.headers["Cache-Control"] = NO_STORE
    view = await service.set_quantity(user_id, sku, body.quantity, body.accepted_price)
    return CartOut.from_domain(view, media)


@router.delete(
    "/items/{sku}",
    response_model=CartOut,
    summary="Remove a product from the cart",
    description="Removing a product that is not in the cart is not an error.",
    responses=problem_responses(401, 404, 503),
)
async def delete_item(
    sku: SkuPath,
    user_id: UserIdDep,
    service: CartServiceDep,
    media: MediaBaseUrlDep,
    response: Response,
) -> CartOut:
    response.headers["Cache-Control"] = NO_STORE
    return CartOut.from_domain(await service.remove(user_id, sku), media)


@router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Empty the cart",
    responses=problem_responses(401, 503),
)
async def clear_cart(user_id: UserIdDep, service: CartServiceDep) -> Response:
    await service.clear(user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers={"Cache-Control": NO_STORE})
