from fastapi import FastAPI

from payments.api import payments
from payments.api.errors import register_payments_errors


def install_api(app: FastAPI) -> None:
    register_payments_errors(app)
    app.include_router(payments.router)
