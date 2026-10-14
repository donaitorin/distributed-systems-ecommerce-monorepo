from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Select, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.application.errors import (
    DuplicateCategoryError,
    DuplicateSkuError,
    ProductNotFoundError,
    UnknownCategoryError,
)
from catalog.domain.product import Category, NewProduct, Product, ProductData
from catalog.infra.models import CategoryModel, ProductModel

SKU_CONSTRAINT = "uq_products_sku"
CATEGORY_FOREIGN_KEY = "fk_products_category_id_categories"


def to_category(model: CategoryModel) -> Category:
    return Category(id=model.id, name=model.name, slug=model.slug)


def to_product(model: ProductModel, category: CategoryModel | None) -> Product:
    return Product(
        id=model.id,
        sku=model.sku,
        name=model.name,
        description=model.description,
        category=to_category(category) if category is not None else None,
        price=model.price,
        stock=model.stock,
        weight_kg=model.weight_kg,
        image_key=model.image_key,
        version=model.version,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class SqlProductRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, sku: str) -> Product | None:
        return await self._fetch_one(sku, lock=False)

    async def get_for_update(self, sku: str) -> Product | None:
        return await self._fetch_one(sku, lock=True)

    async def list(self, limit: int) -> list[Product]:
        statement = (
            self._select_active()
            .order_by(ProductModel.sku)
            .limit(limit)
            .execution_options(populate_existing=True)
        )
        rows = (await self._session.execute(statement)).all()
        return [to_product(product, category) for product, category in rows]

    async def add(self, new_product: NewProduct, now: datetime) -> Product:
        data = new_product.data
        model = ProductModel(
            id=uuid4(),
            sku=new_product.sku,
            name=data.name,
            description=data.description,
            category_id=data.category_id,
            price=data.price,
            stock=data.stock,
            weight_kg=data.weight_kg,
            version=1,
            created_at=now,
            updated_at=now,
        )
        self._session.add(model)
        try:
            await self._session.flush()
        except IntegrityError as error:
            raise _translate(error, new_product.sku) from error
        category = (
            await self._session.get(CategoryModel, data.category_id) if data.category_id else None
        )
        return to_product(model, category)

    async def replace(self, sku: str, data: ProductData, now: datetime) -> Product:
        statement = (
            update(ProductModel)
            .where(ProductModel.sku == sku, ProductModel.deleted_at.is_(None))
            .values(
                name=data.name,
                description=data.description,
                category_id=data.category_id,
                price=data.price,
                stock=data.stock,
                weight_kg=data.weight_kg,
                version=ProductModel.version + 1,
                updated_at=now,
            )
        )
        try:
            await self._session.execute(statement)
        except IntegrityError as error:
            raise _translate(error, sku) from error
        product = await self.get(sku)
        if product is None:
            raise ProductNotFoundError(sku)
        return product

    async def soft_delete(self, sku: str, now: datetime) -> None:
        statement = (
            update(ProductModel)
            .where(ProductModel.sku == sku, ProductModel.deleted_at.is_(None))
            .values(deleted_at=now, updated_at=now, version=ProductModel.version + 1)
        )
        await self._session.execute(statement)

    def _select_active(self) -> Select[ProductModel, CategoryModel]:
        return (
            select(ProductModel, CategoryModel)
            .join(CategoryModel, ProductModel.category_id == CategoryModel.id, isouter=True)
            .where(ProductModel.deleted_at.is_(None))
        )

    async def _fetch_one(self, sku: str, lock: bool) -> Product | None:
        statement = self._select_active().where(ProductModel.sku == sku)
        statement = statement.execution_options(populate_existing=True)
        if lock:
            statement = statement.with_for_update(of=ProductModel)
        row = (await self._session.execute(statement)).first()
        return to_product(row[0], row[1]) if row else None


def _translate(error: IntegrityError, sku: str) -> Exception:
    message = str(error.orig)
    if SKU_CONSTRAINT in message:
        return DuplicateSkuError(sku)
    if CATEGORY_FOREIGN_KEY in message:
        return UnknownCategoryError("category does not exist")
    return error


class SqlCategoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self) -> list[Category]:
        statement = select(CategoryModel).order_by(func.lower(CategoryModel.name))
        models = (await self._session.scalars(statement)).all()
        return [to_category(model) for model in models]

    async def get(self, category_id: UUID) -> Category | None:
        model = await self._session.get(CategoryModel, category_id)
        return to_category(model) if model is not None else None

    async def add(self, name: str, slug: str) -> Category:
        model = CategoryModel(id=uuid4(), name=name, slug=slug)
        self._session.add(model)
        try:
            await self._session.flush()
        except IntegrityError as error:
            raise DuplicateCategoryError(name) from error
        await self._session.refresh(model)
        return to_category(model)
