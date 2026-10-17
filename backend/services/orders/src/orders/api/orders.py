from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Query, Response, status
from fastapi.responses import JSONResponse
from pydantic import AwareDatetime

from ecommerce_auth import AdminUser
from orders.api.dependencies import CustomerIdDep, OrderServiceDep
from orders.api.responses import problem_responses
from orders.api.schemas import (
    OrderAcceptedOut,
    OrderDetailOut,
    OrderIn,
    OrderPageOut,
    PageSize,
)
from orders.application.correlation import current_correlation_id
from orders.application.errors import InvalidDateRangeError, InvalidIdempotencyKeyError
from orders.domain.listing import OrderFilters
from orders.domain.status import OrderStatus

router = APIRouter(prefix="/api/v1/orders", tags=["orders"])
admin_router = APIRouter(prefix="/api/v1/admin/orders", tags=["admin orders"])

NO_STORE = "no-store"
REPLAY_HEADER = "Idempotent-Replay"

StatusQuery = Annotated[OrderStatus | None, Query(description="Only orders in this status")]
CreatedFromQuery = Annotated[
    AwareDatetime | None, Query(description="Created at or after this moment (with time zone)")
]
CreatedToQuery = Annotated[
    AwareDatetime | None, Query(description="Created before this moment (with time zone)")
]
LimitQuery = Annotated[PageSize, Query(description="Page size: 25, 50 or 100")]
CursorQuery = Annotated[str | None, Query(max_length=512)]


def build_filters(
    order_status: OrderStatus | None, created_from: datetime | None, created_to: datetime | None
) -> OrderFilters:
    if created_from is not None and created_to is not None and created_from >= created_to:
        raise InvalidDateRangeError
    return OrderFilters(order_status, created_from, created_to)


@router.post(
    "",
    response_model=OrderAcceptedOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Place an order",
    description=(
        "Creates the order as PENDING and starts the checkout saga. Requires an "
        "Idempotency-Key header: the same key with the same body returns the same "
        "response for 24 hours, the same key with a different body is rejected."
    ),
    responses=problem_responses(400, 401, 422),
)
async def place_order(
    body: OrderIn,
    customer_id: CustomerIdDep,
    service: OrderServiceDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> Response:
    if idempotency_key is None:
        raise InvalidIdempotencyKeyError("the Idempotency-Key header is required")
    placement = await service.place(
        customer_id, idempotency_key, body.to_domain(), current_correlation_id()
    )
    headers = {"Location": f"/api/v1/orders/{placement.order_id}", "Cache-Control": NO_STORE}
    if placement.replayed:
        headers[REPLAY_HEADER] = "true"
    return JSONResponse(placement.body, status_code=placement.status_code, headers=headers)


@router.get(
    "",
    response_model=OrderPageOut,
    summary="List your orders, newest first",
    responses=problem_responses(401, 422),
)
async def list_orders(
    customer_id: CustomerIdDep,
    service: OrderServiceDep,
    response: Response,
    order_status: Annotated[OrderStatus | None, Query(alias="status")] = None,
    limit: LimitQuery = 25,
    cursor: CursorQuery = None,
) -> OrderPageOut:
    response.headers["Cache-Control"] = NO_STORE
    page = await service.list_own(customer_id, OrderFilters(order_status), limit, cursor)
    return OrderPageOut.from_domain(page)


@router.get(
    "/{order_id}",
    response_model=OrderDetailOut,
    summary="Get one of your orders with its lines, totals and status history",
    responses=problem_responses(401, 404, 422),
)
async def get_order(
    order_id: UUID, customer_id: CustomerIdDep, service: OrderServiceDep, response: Response
) -> OrderDetailOut:
    response.headers["Cache-Control"] = NO_STORE
    return OrderDetailOut.from_domain(await service.get_own(customer_id, order_id))


@admin_router.get(
    "",
    response_model=OrderPageOut,
    summary="List every order, newest first (admin)",
    responses=problem_responses(401, 403, 422),
)
async def list_all_orders(
    _admin: AdminUser,
    service: OrderServiceDep,
    response: Response,
    order_status: Annotated[OrderStatus | None, Query(alias="status")] = None,
    created_from: CreatedFromQuery = None,
    created_to: CreatedToQuery = None,
    limit: LimitQuery = 25,
    cursor: CursorQuery = None,
) -> OrderPageOut:
    response.headers["Cache-Control"] = NO_STORE
    filters = build_filters(order_status, created_from, created_to)
    return OrderPageOut.from_domain(await service.list_all(filters, limit, cursor))


@admin_router.get(
    "/{order_id}",
    response_model=OrderDetailOut,
    summary="Get any order (admin)",
    responses=problem_responses(401, 403, 404, 422),
)
async def get_any_order(
    order_id: UUID, _admin: AdminUser, service: OrderServiceDep, response: Response
) -> OrderDetailOut:
    response.headers["Cache-Control"] = NO_STORE
    return OrderDetailOut.from_domain(await service.get_any(order_id))
