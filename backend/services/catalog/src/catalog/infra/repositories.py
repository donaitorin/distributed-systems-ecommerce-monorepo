from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Select, func, or_, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.application.errors import (
    DuplicateCategoryError,
    DuplicateSkuError,
    ProductNotFoundError,
    SearchTimeoutError,
    UnknownCategoryError,
)
from catalog.domain.csv_import import ImportableRow
from catalog.domain.imports import (
    ChangedProduct,
    ExistingProduct,
    Progress,
    UpsertResult,
    classify,
)
from catalog.domain.listing import (
    ListedProduct,
    PageRequest,
    ProductFilters,
    SearchResult,
    Sort,
    TextMode,
    Total,
)
from catalog.domain.product import Category, NewProduct, Product, ProductData
from catalog.infra.explain import ExplainJson, parse_plan
from catalog.infra.models import CategoryModel, ProductModel
from catalog.infra.search import (
    COUNT_CAP,
    build_matching_ids,
    build_search_statement,
    build_text_probe,
    statement_timeout_statement,
    trigram_threshold_statement,
)

QUERY_CANCELED = "57014"
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
    def __init__(self, session: AsyncSession, search_timeout_ms: int) -> None:
        self._session = session
        self._search_timeout_ms = search_timeout_ms
        self._timeout_applied = False

    async def get(self, sku: str) -> Product | None:
        return await self._fetch_one(sku, lock=False)

    async def get_for_update(self, sku: str) -> Product | None:
        return await self._fetch_one(sku, lock=True)

    async def search(self, filters: ProductFilters, sort: Sort, page: PageRequest) -> SearchResult:
        async with self._bounded_search():
            mode = await self._prepare_text_search(filters, page.mode)
            statement = build_search_statement(filters, sort, page, mode)
            rows = (
                await self._session.execute(statement.execution_options(populate_existing=True))
            ).all()
        listed = [
            ListedProduct(to_product(product, category), score) for product, category, score in rows
        ]
        return SearchResult(listed, mode)

    async def count(self, filters: ProductFilters, mode: TextMode | None) -> Total:
        async with self._bounded_search():
            resolved = await self._prepare_text_search(filters, mode)
            matching = build_matching_ids(filters, resolved)
            plan = parse_plan(await self._session.scalar(ExplainJson(matching)))
            estimate = int(plan["Plan Rows"])
            if estimate > COUNT_CAP:
                return Total(estimate, exact=False)
            capped = select(func.count()).select_from(matching.limit(COUNT_CAP + 1).subquery())
            counted = int(await self._session.scalar(capped) or 0)
        if counted > COUNT_CAP:
            return Total(max(estimate, counted), exact=False)
        return Total(counted, exact=True)

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

    async def soft_delete(self, sku: str, now: datetime) -> int:
        statement = (
            update(ProductModel)
            .where(ProductModel.sku == sku, ProductModel.deleted_at.is_(None))
            .values(deleted_at=now, updated_at=now, version=ProductModel.version + 1)
            .returning(ProductModel.version)
        )
        version = (await self._session.execute(statement)).scalar_one_or_none()
        if version is None:
            raise ProductNotFoundError(sku)
        return int(version)

    async def set_image(self, sku: str, image_key: str | None, now: datetime) -> Product:
        statement = (
            update(ProductModel)
            .where(ProductModel.sku == sku, ProductModel.deleted_at.is_(None))
            .values(image_key=image_key, version=ProductModel.version + 1, updated_at=now)
        )
        await self._session.execute(statement)
        product = await self.get(sku)
        if product is None:
            raise ProductNotFoundError(sku)
        return product

    async def upsert_many(self, rows: Sequence[ImportableRow], now: datetime) -> UpsertResult:
        existing = await self.existing([row.product.sku for row in rows])
        created, updated, restored, unchanged = classify(rows, existing)
        values = [
            {
                "id": uuid4(),
                "sku": row.product.sku,
                "name": row.product.data.name,
                "description": row.product.data.description,
                "category_id": row.product.data.category_id,
                "price": row.product.data.price,
                "stock": row.product.data.stock,
                "weight_kg": row.product.data.weight_kg,
                "version": 1,
                "created_at": now,
                "updated_at": now,
            }
            for row in rows
        ]
        statement = pg_insert(ProductModel).values(values)
        incoming = statement.excluded
        statement = statement.on_conflict_do_update(
            index_elements=[ProductModel.sku],
            set_={
                "name": incoming.name,
                "description": incoming.description,
                "category_id": incoming.category_id,
                "price": incoming.price,
                "stock": incoming.stock,
                "weight_kg": incoming.weight_kg,
                "version": ProductModel.version + 1,
                "updated_at": now,
                "deleted_at": None,
            },
            where=or_(
                ProductModel.deleted_at.is_not(None),
                tuple_(
                    ProductModel.name,
                    ProductModel.description,
                    ProductModel.category_id,
                    ProductModel.price,
                    ProductModel.stock,
                    ProductModel.weight_kg,
                ).is_distinct_from(
                    tuple_(
                        incoming.name,
                        incoming.description,
                        incoming.category_id,
                        incoming.price,
                        incoming.stock,
                        incoming.weight_kg,
                    )
                ),
            ),
        )
        returning = statement.returning(
            ProductModel.sku,
            ProductModel.name,
            ProductModel.price,
            ProductModel.stock,
            ProductModel.image_key,
            ProductModel.version,
        )
        changed = tuple(
            ChangedProduct(*row) for row in (await self._session.execute(returning)).all()
        )
        progress = Progress(len(rows), created, updated, restored, unchanged)
        return UpsertResult(progress, changed)

    async def existing(self, skus: Sequence[str]) -> Mapping[str, ExistingProduct]:
        statement = select(ProductModel).where(ProductModel.sku.in_(list(skus)))
        models = (
            await self._session.execute(statement.execution_options(populate_existing=True))
        ).scalars()
        return {
            model.sku: ExistingProduct(
                deleted=model.deleted_at is not None,
                data=ProductData(
                    name=model.name,
                    description=model.description,
                    category_id=model.category_id,
                    price=model.price,
                    stock=model.stock,
                    weight_kg=model.weight_kg,
                ),
            )
            for model in models
        }

    @asynccontextmanager
    async def _bounded_search(self) -> AsyncIterator[None]:
        try:
            if not self._timeout_applied:
                await self._session.execute(statement_timeout_statement(self._search_timeout_ms))
                self._timeout_applied = True
            yield
        except DBAPIError as error:
            if getattr(error.orig, "sqlstate", None) == QUERY_CANCELED:
                raise SearchTimeoutError(self._search_timeout_ms) from error
            raise

    async def _prepare_text_search(
        self, filters: ProductFilters, requested: TextMode | None
    ) -> TextMode | None:
        if filters.query is None:
            return None
        mode = requested
        if mode is None:
            found = await self._session.scalar(build_text_probe(filters))
            mode = TextMode.FULL_TEXT if found else TextMode.TRIGRAM
        if mode is TextMode.TRIGRAM:
            await self._session.execute(trigram_threshold_statement())
        return mode

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
