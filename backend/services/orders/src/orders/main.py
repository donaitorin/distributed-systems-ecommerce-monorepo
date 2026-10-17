import os
from collections.abc import Callable
from datetime import datetime

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from ecommerce_auth import create_token_verifier
from ecommerce_web import ServiceSettings, create_app
from orders.api import install_api
from orders.application.clock import utc_now
from orders.application.orders import OrderService
from orders.application.ports import UnitOfWorkFactory
from orders.infra.database import create_engine, create_session_factory, database_readiness_check
from orders.infra.unit_of_work import SqlAlchemyUnitOfWork
from orders.settings import OrdersSettings

SERVICE_NAME = "orders"


def create_orders_app(
    settings: OrdersSettings,
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
    app.state.order_service = OrderService(work, clock)
    install_api(app)
    return app


def build() -> FastAPI:
    return create_orders_app(OrdersSettings.from_env(os.environ))
