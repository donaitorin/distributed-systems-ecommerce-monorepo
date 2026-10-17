import os

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from ecommerce_auth import create_token_verifier
from ecommerce_web import ServiceSettings, create_app
from payments.api import install_api
from payments.application.ports import UnitOfWorkFactory
from payments.application.queries import PaymentQueries
from payments.infra.database import create_engine, create_session_factory, database_readiness_check
from payments.infra.unit_of_work import SqlAlchemyUnitOfWork
from payments.settings import PaymentsSettings

SERVICE_NAME = "payments"


def create_payments_app(
    settings: PaymentsSettings,
    engine: AsyncEngine | None = None,
    unit_of_work: UnitOfWorkFactory | None = None,
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
    app.state.payment_queries = PaymentQueries(work)
    install_api(app)
    return app


def build() -> FastAPI:
    return create_payments_app(PaymentsSettings.from_env(os.environ))
