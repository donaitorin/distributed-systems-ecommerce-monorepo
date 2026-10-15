from fastapi import FastAPI

from accounts.api import accounts
from accounts.api.errors import register_accounts_errors


def install_api(app: FastAPI) -> None:
    register_accounts_errors(app)
    app.include_router(accounts.router)
