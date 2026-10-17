from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response

from ecommerce_auth import CustomerUser, InvalidTokenError, Role
from payments.api.schemas import PaymentOut, ProblemOut
from payments.application.queries import PaymentQueries

router = APIRouter(prefix="/api/v1/payments", tags=["payments"])


def get_queries(request: Request) -> PaymentQueries:
    queries: PaymentQueries = request.app.state.payment_queries
    return queries


QueriesDep = Annotated[PaymentQueries, Depends(get_queries)]


@router.get(
    "/{order_id}",
    response_model=PaymentOut,
    summary="Get the payment of an order (its owner or an admin)",
    description="Only the last 4 digits of the card are ever exposed.",
    responses={
        401: {"model": ProblemOut, "description": "Missing, invalid or expired access token"},
        404: {"model": ProblemOut, "description": "No such payment, or it belongs to someone else"},
        422: {"model": ProblemOut, "description": "Invalid order id"},
    },
)
async def get_payment(
    order_id: UUID, user: CustomerUser, queries: QueriesDep, response: Response
) -> PaymentOut:
    try:
        user_id = UUID(user.user_id)
    except ValueError as error:
        raise InvalidTokenError("The access token is invalid or expired") from error
    response.headers["Cache-Control"] = "no-store"
    payment = await queries.of_order(order_id, user_id, user.role is Role.ADMIN)
    return PaymentOut.from_domain(payment)
