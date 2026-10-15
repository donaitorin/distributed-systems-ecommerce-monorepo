import os
from collections.abc import Callable
from datetime import datetime

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from auth.api import install_api
from auth.application.clock import utc_now
from auth.application.ports import PasswordHasher, UnitOfWorkFactory
from auth.application.registration import RegistrationService
from auth.application.service import AuthService, RefreshPolicy
from auth.infra.database import create_engine, create_session_factory, database_readiness_check
from auth.infra.hashing import Argon2idHasher
from auth.infra.keys import KeyStore, load_key_store
from auth.infra.signer import JwtAccessTokenIssuer
from auth.infra.unit_of_work import SqlAlchemyUnitOfWork
from auth.settings import AuthSettings
from ecommerce_web import ServiceSettings, create_app

SERVICE_NAME = "auth"


def create_auth_app(
    settings: AuthSettings,
    engine: AsyncEngine | None = None,
    unit_of_work: UnitOfWorkFactory | None = None,
    clock: Callable[[], datetime] = utc_now,
    keys: KeyStore | None = None,
    hasher: PasswordHasher | None = None,
) -> FastAPI:
    engine = engine or create_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    key_store = keys or load_key_store(
        settings.keys_dir, settings.active_kid, settings.generate_key_if_missing
    )
    password_hasher = hasher or Argon2idHasher(settings.hashing)
    work = unit_of_work or (lambda: SqlAlchemyUnitOfWork(session_factory))
    issuer = JwtAccessTokenIssuer(
        key_store, settings.issuer, settings.audience, settings.access_token_ttl
    )
    app = create_app(
        ServiceSettings(name=SERVICE_NAME, log_level=settings.log_level),
        readiness_checks=[database_readiness_check(engine)],
        on_shutdown=[engine.dispose],
        root_path=settings.root_path,
    )
    app.state.session_factory = session_factory
    app.state.jwks = key_store.jwks_document()
    app.state.registration_service = RegistrationService(work, password_hasher, clock)
    app.state.auth_service = AuthService(
        work,
        password_hasher,
        issuer,
        clock,
        RefreshPolicy(
            settings.refresh_token_ttl, settings.refresh_family_ttl, settings.refresh_reuse_grace
        ),
    )
    install_api(app)
    return app


def build() -> FastAPI:
    return create_auth_app(AuthSettings.from_env(os.environ))
