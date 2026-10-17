from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request

from ecommerce_auth import CustomerUser, InvalidTokenError
from orders.application.orders import OrderService


def get_order_service(request: Request) -> OrderService:
    service: OrderService = request.app.state.order_service
    return service


def get_customer_id(user: CustomerUser) -> UUID:
    try:
        return UUID(user.user_id)
    except ValueError as error:
        raise InvalidTokenError("The access token is invalid or expired") from error


OrderServiceDep = Annotated[OrderService, Depends(get_order_service)]
CustomerIdDep = Annotated[UUID, Depends(get_customer_id)]
