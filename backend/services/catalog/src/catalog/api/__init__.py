from fastapi import FastAPI

from catalog.api import categories, images, imports, products
from catalog.api.errors import register_catalog_errors


def install_api(app: FastAPI) -> None:
    register_catalog_errors(app)
    app.include_router(products.router)
    app.include_router(images.router)
    app.include_router(imports.router)
    app.include_router(categories.router)
