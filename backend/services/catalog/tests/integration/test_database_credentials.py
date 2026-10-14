from collections.abc import Callable

import pytest
from sqlalchemy import make_url, text

from catalog.infra.database import create_engine
from catalog.settings import database_url_from_env

pytestmark = pytest.mark.integration

HOSTILE_PASSWORD = "p@ss:w/rd%#?&=' \"x ünï"


async def test_a_password_full_of_url_special_characters_still_connects(
    create_login_role: Callable[[str, str, str], None],
    postgres_host_and_port: tuple[str, int],
    empty_database_url: str,
) -> None:
    create_login_role(empty_database_url, "service_user", HOSTILE_PASSWORD)
    host, port = postgres_host_and_port
    url = database_url_from_env(
        {
            "CATALOG_DB_HOST": host,
            "CATALOG_DB_PORT": str(port),
            "CATALOG_DB_NAME": make_url(empty_database_url).database or "",
            "CATALOG_DB_USER": "service_user",
            "CATALOG_DB_PASSWORD": HOSTILE_PASSWORD,
        }
    )
    engine = create_engine(url)

    try:
        async with engine.connect() as connection:
            assert await connection.scalar(text("SELECT current_user")) == "service_user"
    finally:
        await engine.dispose()
