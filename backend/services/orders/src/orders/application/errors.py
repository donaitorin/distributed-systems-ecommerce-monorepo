from uuid import UUID


class ApplicationError(Exception):
    pass


class OrderNotFoundError(ApplicationError):
    def __init__(self, order_id: UUID) -> None:
        super().__init__(f"order {order_id} not found")
        self.order_id = order_id


class InvalidIdempotencyKeyError(ApplicationError):
    pass


class IdempotencyKeyReusedError(ApplicationError):
    def __init__(self, key: str) -> None:
        super().__init__("the idempotency key was already used with a different request body")
        self.key = key


class InvalidDateRangeError(ApplicationError):
    def __init__(self) -> None:
        super().__init__("created_from must be before created_to")
