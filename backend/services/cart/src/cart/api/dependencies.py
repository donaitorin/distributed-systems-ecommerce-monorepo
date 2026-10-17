from typing import Annotated

from fastapi import Depends, Request

from cart.application.carts import CartService
from ecommerce_auth import CustomerUser


def get_cart_service(request: Request) -> CartService:
    service: CartService = request.app.state.cart_service
    return service


def get_media_base_url(request: Request) -> str:
    base_url: str = request.app.state.media_base_url
    return base_url


def get_user_id(user: CustomerUser) -> str:
    return user.user_id


CartServiceDep = Annotated[CartService, Depends(get_cart_service)]
MediaBaseUrlDep = Annotated[str, Depends(get_media_base_url)]
UserIdDep = Annotated[str, Depends(get_user_id)]
