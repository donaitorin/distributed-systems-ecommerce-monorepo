import os

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from catalog.infra.database import create_engine, create_session_factory, database_readiness_check
from catalog.settings import CatalogSettings
from ecommerce_auth import create_token_verifier
from ecommerce_web import ServiceSettings, create_app

SERVICE_NAME = "catalog"


def create_catalog_app(settings: CatalogSettings, engine: AsyncEngine | None = None) -> FastAPI:
    engine = engine or create_engine(settings.database_url)
    app = create_app(
        ServiceSettings(name=SERVICE_NAME, log_level=settings.log_level),
        readiness_checks=[database_readiness_check(engine)],
        token_verifier=create_token_verifier(settings.jwt),
        on_shutdown=[engine.dispose],
        root_path=settings.root_path,
    )
    app.state.session_factory = create_session_factory(engine)
    return app


def build() -> FastAPI:
    return create_catalog_app(CatalogSettings.from_env(os.environ))
