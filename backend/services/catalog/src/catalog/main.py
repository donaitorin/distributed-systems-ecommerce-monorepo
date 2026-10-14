import os
from collections.abc import Callable
from datetime import datetime

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from catalog.api import install_api
from catalog.application.categories import CategoryService
from catalog.application.ports import UnitOfWorkFactory
from catalog.application.products import ProductService, utc_now
from catalog.infra.database import create_engine, create_session_factory, database_readiness_check
from catalog.infra.unit_of_work import SqlAlchemyUnitOfWork
from catalog.settings import CatalogSettings
from ecommerce_auth import create_token_verifier
from ecommerce_web import ServiceSettings, create_app

SERVICE_NAME = "catalog"


def create_catalog_app(
    settings: CatalogSettings,
    engine: AsyncEngine | None = None,
    unit_of_work: UnitOfWorkFactory | None = None,
    clock: Callable[[], datetime] = utc_now,
) -> FastAPI:
    engine = engine or create_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    app = create_app(
        ServiceSettings(name=SERVICE_NAME, log_level=settings.log_level),
        readiness_checks=[database_readiness_check(engine)],
        token_verifier=create_token_verifier(settings.jwt),
        on_shutdown=[engine.dispose],
        root_path=settings.root_path,
    )
    work = unit_of_work or (lambda: SqlAlchemyUnitOfWork(session_factory))
    app.state.session_factory = session_factory
    app.state.product_service = ProductService(work, clock)
    app.state.category_service = CategoryService(work)
    install_api(app)
    return app


def build() -> FastAPI:
    return create_catalog_app(CatalogSettings.from_env(os.environ))
