from fastapi import FastAPI

from orders.api import orders
from orders.api.errors import register_orders_errors


def install_api(app: FastAPI) -> None:
    register_orders_errors(app)
    app.include_router(orders.router)
    app.include_router(orders.admin_router)
