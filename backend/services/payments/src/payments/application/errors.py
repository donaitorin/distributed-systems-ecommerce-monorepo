from uuid import UUID


class ApplicationError(Exception):
    pass


class PaymentNotFoundError(ApplicationError):
    def __init__(self, order_id: UUID) -> None:
        super().__init__(f"no payment for order {order_id}")
        self.order_id = order_id


class ProviderUnavailableError(ApplicationError):
    pass
