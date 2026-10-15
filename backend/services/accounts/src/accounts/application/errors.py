from uuid import UUID


class ApplicationError(Exception):
    pass


class AddressLimitReachedError(ApplicationError):
    def __init__(self, limit: int) -> None:
        super().__init__(f"a user can keep at most {limit} addresses")
        self.limit = limit


class AddressNotFoundError(ApplicationError):
    def __init__(self, address_id: UUID) -> None:
        super().__init__(f"address {address_id} not found")
        self.address_id = address_id


class ProfileNotFoundError(ApplicationError):
    def __init__(self, user_id: UUID) -> None:
        super().__init__(f"profile {user_id} not found")
        self.user_id = user_id
