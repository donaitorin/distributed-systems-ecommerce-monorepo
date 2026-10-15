from fastapi import FastAPI

from auth.api import auth
from auth.api.errors import register_auth_errors


def install_api(app: FastAPI) -> None:
    register_auth_errors(app)
    app.include_router(auth.router)
