from typing import Any

from sqlalchemy import (
    ColumnElement,
    Double,
    Float,
    Numeric,
    Select,
    cast,
    exists,
    func,
    literal,
    literal_column,
    null,
    select,
    tuple_,
)
from sqlalchemy.types import DateTime

from catalog.domain.listing import Direction, PageRequest, ProductFilters, Sort, TextMode
from catalog.infra.models import CategoryModel, ProductModel

TEXT_SEARCH_CONFIG: ColumnElement[Any] = literal_column("'english'::regconfig")
TRIGRAM_THRESHOLD_SETTING = "pg_trgm.word_similarity_threshold"
TRIGRAM_THRESHOLD = "0.5"
RANK_NORMALIZATION = 2 | 32
COUNT_CAP = 1000


def statement_timeout_statement(timeout_ms: int) -> Select[tuple[str]]:
    return select(func.set_config("statement_timeout", str(timeout_ms), True))


def trigram_threshold_statement() -> Select[tuple[str]]:
    return select(func.set_config(TRIGRAM_THRESHOLD_SETTING, TRIGRAM_THRESHOLD, True))


def _full_text_match(query: str) -> ColumnElement[bool]:
    return ProductModel.search_vector.op("@@")(_tsquery(query))


def _tsquery(query: str) -> ColumnElement[Any]:
    return func.websearch_to_tsquery(TEXT_SEARCH_CONFIG, query)


def _trigram_match(query: str) -> ColumnElement[bool]:
    return literal(query).op("<%")(ProductModel.name)


def _text_match(query: str, mode: TextMode | None) -> ColumnElement[bool]:
    return _full_text_match(query) if mode is TextMode.FULL_TEXT else _trigram_match(query)


def _relevance(query: str, mode: TextMode | None) -> ColumnElement[Any]:
    if mode is TextMode.TRIGRAM:
        return cast(func.word_similarity(query, ProductModel.name, type_=Float), Double)
    rank = func.ts_rank(
        ProductModel.search_vector, _tsquery(query), RANK_NORMALIZATION, type_=Float
    )
    return cast(rank, Double)


def filter_conditions(filters: ProductFilters, mode: TextMode | None) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = [ProductModel.deleted_at.is_(None)]
    if filters.query is not None:
        conditions.append(_text_match(filters.query, mode))
    if filters.category is not None:
        category_id = select(CategoryModel.id).where(CategoryModel.slug == filters.category)
        conditions.append(ProductModel.category_id == category_id.scalar_subquery())
    if filters.min_price is not None:
        conditions.append(ProductModel.price >= filters.min_price)
    if filters.max_price is not None:
        conditions.append(ProductModel.price <= filters.max_price)
    if filters.in_stock:
        conditions.append(ProductModel.stock > 0)
    return conditions


def build_text_probe(filters: ProductFilters) -> Select[Any]:
    matching = select(ProductModel.id).where(*filter_conditions(filters, TextMode.FULL_TEXT))
    return select(exists(matching))


def build_matching_ids(filters: ProductFilters, mode: TextMode | None) -> Select[Any]:
    return select(ProductModel.id).where(*filter_conditions(filters, mode))


def build_search_statement(
    filters: ProductFilters, sort: Sort, page: PageRequest, mode: TextMode | None
) -> Select[Any]:
    score = _score(filters, sort, mode)
    sort_key = _sort_key(sort, score)
    descending = _descending(sort)
    ordered_descending = descending if page.direction is Direction.AFTER else not descending
    statement = (
        select(ProductModel, CategoryModel, score.label("score"))
        .join(CategoryModel, ProductModel.category_id == CategoryModel.id, isouter=True)
        .where(*filter_conditions(filters, mode))
    )
    if page.position is not None:
        row = tuple_(sort_key, ProductModel.id)
        boundary = tuple_(
            literal(page.position.key, _key_type(sort)),
            literal(page.position.id, ProductModel.id.type),
        )
        statement = statement.where(row < boundary if ordered_descending else row > boundary)
    ordering = (
        (sort_key.desc(), ProductModel.id.desc())
        if ordered_descending
        else (sort_key.asc(), ProductModel.id.asc())
    )
    return statement.order_by(*ordering).limit(page.limit + 1)


def _score(filters: ProductFilters, sort: Sort, mode: TextMode | None) -> ColumnElement[Any]:
    if sort is Sort.RELEVANCE and filters.query is not None:
        return _relevance(filters.query, mode)
    return null()


def _sort_key(sort: Sort, score: ColumnElement[Any]) -> Any:
    match sort:
        case Sort.NEWEST:
            return ProductModel.created_at
        case Sort.PRICE_ASC | Sort.PRICE_DESC:
            return ProductModel.price
        case Sort.RELEVANCE:
            return score


def _key_type(sort: Sort) -> DateTime | Numeric[Any] | Double[Any]:
    match sort:
        case Sort.NEWEST:
            return DateTime(timezone=True)
        case Sort.PRICE_ASC | Sort.PRICE_DESC:
            return Numeric(12, 2)
        case Sort.RELEVANCE:
            return Double()


def _descending(sort: Sort) -> bool:
    return sort is not Sort.PRICE_ASC
