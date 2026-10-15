import asyncio
import logging
import os
from collections.abc import Mapping
from uuid import uuid4

from auth.application.errors import EmailTakenError
from auth.application.ports import PasswordHasher, UnitOfWorkFactory
from auth.application.registration import RegistrationService
from auth.domain.user import Role
from auth.infra.database import create_engine, create_session_factory
from auth.infra.hashing import Argon2idHasher
from auth.infra.unit_of_work import SqlAlchemyUnitOfWork
from auth.settings import AuthSettings, hashing_from_env
from ecommerce_observability import configure_logging

logger = logging.getLogger(__name__)

SERVICE_NAME = "auth-seed"
ADMIN_EMAIL_VARIABLE = "AUTH_ADMIN_EMAIL"
ADMIN_PASSWORD_VARIABLE = "AUTH_ADMIN_PASSWORD"


async def seed_admin(
    unit_of_work: UnitOfWorkFactory, hasher: PasswordHasher, email: str, password: str
) -> bool:
    try:
        await RegistrationService(unit_of_work, hasher).register(
            email, password, uuid4(), Role.ADMIN
        )
    except EmailTakenError:
        return False
    return True


async def run(environ: Mapping[str, str]) -> bool | None:
    email = environ.get(ADMIN_EMAIL_VARIABLE)
    password = environ.get(ADMIN_PASSWORD_VARIABLE)
    if not email or not password:
        logger.info("admin seed skipped: %s and %s are not set", *seed_variables())
        return None
    settings = AuthSettings.from_env(environ)
    engine = create_engine(settings.database_url)
    try:
        created = await seed_admin(
            lambda: SqlAlchemyUnitOfWork(create_session_factory(engine)),
            Argon2idHasher(hashing_from_env(environ)),
            email,
            password,
        )
    finally:
        await engine.dispose()
    logger.info("admin seed finished", extra={"admin_created": created})
    return created


def seed_variables() -> tuple[str, str]:
    return ADMIN_EMAIL_VARIABLE, ADMIN_PASSWORD_VARIABLE


def main() -> None:
    configure_logging(SERVICE_NAME, os.environ.get("LOG_LEVEL", "INFO"))
    asyncio.run(run(os.environ))


if __name__ == "__main__":
    main()
