from uuid import UUID

from payments.application.errors import PaymentNotFoundError
from payments.application.ports import UnitOfWorkFactory
from payments.domain.payment import Payment


class PaymentQueries:
    def __init__(self, unit_of_work: UnitOfWorkFactory) -> None:
        self._unit_of_work = unit_of_work

    async def of_order(self, order_id: UUID, user_id: UUID, is_admin: bool) -> Payment:
        async with self._unit_of_work() as uow:
            payment = await uow.payments.get_by_order(order_id)
        if payment is None or not (is_admin or payment.customer_id == user_id):
            raise PaymentNotFoundError(order_id)
        return payment
