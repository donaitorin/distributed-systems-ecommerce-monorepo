import os
from collections.abc import Callable
from datetime import datetime

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from accounts.api import install_api
from accounts.application.accounts import AccountService
from accounts.application.clock import utc_now
from accounts.application.ports import UnitOfWorkFactory
from accounts.infra.database import create_engine, create_session_factory, database_readiness_check
from accounts.infra.unit_of_work import SqlAlchemyUnitOfWork
from accounts.settings import AccountsSettings
from ecommerce_auth import create_token_verifier
from ecommerce_web import ServiceSettings, create_app

SERVICE_NAME = "accounts"


def create_accounts_app(
    settings: AccountsSettings,
    engine: AsyncEngine | None = None,
    unit_of_work: UnitOfWorkFactory | None = None,
    clock: Callable[[], datetime] = utc_now,
) -> FastAPI:
    engine = engine or create_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    work = unit_of_work or (lambda: SqlAlchemyUnitOfWork(session_factory))
    app = create_app(
        ServiceSettings(name=SERVICE_NAME, log_level=settings.log_level),
        readiness_checks=[database_readiness_check(engine)],
        token_verifier=create_token_verifier(settings.jwt),
        on_shutdown=[engine.dispose],
        root_path=settings.root_path,
    )
    app.state.session_factory = session_factory
    app.state.account_service = AccountService(work, clock)
    install_api(app)
    return app


def build() -> FastAPI:
    return create_accounts_app(AccountsSettings.from_env(os.environ))
