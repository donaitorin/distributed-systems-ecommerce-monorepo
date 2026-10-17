from fastapi import FastAPI

from cart.api import carts
from cart.api.errors import register_cart_errors


def install_api(app: FastAPI) -> None:
    register_cart_errors(app)
    app.include_router(carts.router)
