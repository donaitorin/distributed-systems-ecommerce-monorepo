import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import make_url
from testcontainers.community.postgres import PostgresContainer

POSTGRES_IMAGE = "postgres:17.11-alpine"


class PostgresServer:
    def __init__(self, container: PostgresContainer) -> None:
        self._container = container

    def create_database(self) -> str:
        name = f"catalog_{uuid.uuid4().hex[:12]}"
        self._container.exec(
            [
                "psql",
                "--username",
                self._container.username,
                "--dbname",
                self._container.dbname,
                "-c",
                f"CREATE DATABASE {name}",
            ]
        )
        base = self._container.get_connection_url(driver="asyncpg")
        return base.rsplit("/", 1)[0] + f"/{name}"

    def create_login_role(self, database_url: str, role: str, password: str) -> None:
        database = make_url(database_url).database or ""
        escaped = password.replace("'", "''")
        for statement in (
            f"CREATE ROLE {role} LOGIN PASSWORD '{escaped}'",
            f"GRANT ALL ON DATABASE {database} TO {role}",
            f"GRANT ALL ON SCHEMA public TO {role}",
        ):
            self._container.exec(
                [
                    "psql",
                    "--username",
                    self._container.username,
                    "--dbname",
                    database if "SCHEMA" in statement else self._container.dbname,
                    "-c",
                    statement,
                ]
            )

    def create_owned_database(self, role: str, password: str) -> str:
        name = f"catalog_{uuid.uuid4().hex[:12]}"
        escaped = password.replace("'", "''")
        for statement in (
            f"CREATE ROLE {role} LOGIN PASSWORD '{escaped}'",
            f"CREATE DATABASE {name} OWNER {role}",
        ):
            self._container.exec(
                [
                    "psql",
                    "--username",
                    self._container.username,
                    "--dbname",
                    self._container.dbname,
                    "-c",
                    statement,
                ]
            )
        url = make_url(self._container.get_connection_url(driver="asyncpg"))
        return url.set(username=role, password=password, database=name).render_as_string(
            hide_password=False
        )

    def host_and_port(self) -> tuple[str, int]:
        url = make_url(self._container.get_connection_url(driver="asyncpg"))
        return url.host or "localhost", url.port or 5432


@contextmanager
def run_postgres() -> Iterator[PostgresServer]:
    with PostgresContainer(POSTGRES_IMAGE, driver="asyncpg") as container:
        yield PostgresServer(container)
