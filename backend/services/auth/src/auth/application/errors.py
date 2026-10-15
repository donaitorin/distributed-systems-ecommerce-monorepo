from auth.domain.errors import DomainError


class EmailTakenError(DomainError):
    def __init__(self, email: str) -> None:
        super().__init__(f"email {email} is already registered")
        self.email = email


class InvalidCredentialsError(DomainError):
    pass


class InvalidRefreshTokenError(DomainError):
    pass
