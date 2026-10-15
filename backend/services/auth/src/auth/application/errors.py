from auth.domain.errors import DomainError


class EmailTakenError(DomainError):
    def __init__(self, email: str) -> None:
        super().__init__(f"email {email} is already registered")
        self.email = email


class UserNotFoundError(DomainError):
    def __init__(self, user_id: object) -> None:
        super().__init__(f"user {user_id} not found")
        self.user_id = user_id


class SelfRoleChangeError(DomainError):
    pass


class InvalidCredentialsError(DomainError):
    pass


class InvalidRefreshTokenError(DomainError):
    pass
