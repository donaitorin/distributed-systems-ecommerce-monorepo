import json
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from fastapi import FastAPI

from accounts.main import create_accounts_app
from accounts.settings import AccountsSettings
from auth.main import create_auth_app
from auth.settings import AuthSettings
from cart.main import create_cart_app
from cart.settings import CartSettings
from catalog.main import create_catalog_app
from catalog.settings import CatalogSettings
from orders.main import create_orders_app
from orders.settings import OrdersSettings

PLACEHOLDER_ENVIRONMENT: Mapping[str, str] = {
    "JWT_JWKS_URL": "http://auth.invalid/api/v1/auth/.well-known/jwks.json",
    "JWT_ISSUER": "ecommerce-auth",
    "JWT_AUDIENCE": "ecommerce-api",
    "OBJECT_STORAGE_ACCESS_KEY": "placeholder",
    "OBJECT_STORAGE_SECRET_KEY": "placeholder",
    "OBJECT_STORAGE_REGION": "us-east-1",
    "OBJECT_STORAGE_ENDPOINT": "http://object-storage.invalid:8333",
    "OBJECT_STORAGE_MEDIA_BUCKET": "media",
    "MEDIA_PUBLIC_BASE_URL": "http://localhost/media",
}


def database_environment(prefix: str) -> dict[str, str]:
    return {
        f"{prefix}_DB_USER": "placeholder",
        f"{prefix}_DB_PASSWORD": "placeholder",
        f"{prefix}_DB_HOST": "db.invalid",
        f"{prefix}_DB_NAME": "placeholder",
    }


def build_auth() -> FastAPI:
    environment = {**PLACEHOLDER_ENVIRONMENT, **database_environment("AUTH")}
    with tempfile.TemporaryDirectory() as keys_directory:
        environment["AUTH_KEYS_DIR"] = keys_directory
        environment["AUTH_GENERATE_KEY_IF_MISSING"] = "true"
        return create_auth_app(AuthSettings.from_env(environment))


def build_catalog() -> FastAPI:
    environment = {**PLACEHOLDER_ENVIRONMENT, **database_environment("CATALOG")}
    return create_catalog_app(CatalogSettings.from_env(environment))


def build_accounts() -> FastAPI:
    environment = {**PLACEHOLDER_ENVIRONMENT, **database_environment("ACCOUNTS")}
    return create_accounts_app(AccountsSettings.from_env(environment))


def build_cart() -> FastAPI:
    environment = {
        **PLACEHOLDER_ENVIRONMENT,
        "REDIS_CART_HOST": "redis.invalid",
        "REDIS_CART_PASSWORD": "placeholder",
    }
    return create_cart_app(CartSettings.from_env(environment))


def build_orders() -> FastAPI:
    environment = {**PLACEHOLDER_ENVIRONMENT, **database_environment("ORDERS")}
    return create_orders_app(OrdersSettings.from_env(environment))


SERVICES: Mapping[str, Callable[[], FastAPI]] = {
    "auth": build_auth,
    "catalog": build_catalog,
    "accounts": build_accounts,
    "cart": build_cart,
    "orders": build_orders,
}


def render(app: FastAPI) -> str:
    return json.dumps(app.openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: Sequence[str]) -> int:
    if len(argv) != 1:
        sys.stderr.write("usage: dump_openapi.py <output-directory>\n")
        return 2
    output = Path(argv[0])
    output.mkdir(parents=True, exist_ok=True)
    for name, build in SERVICES.items():
        (output / f"{name}.json").write_text(render(build()), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
