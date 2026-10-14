from http import HTTPStatus


class AuthError(Exception):
    status = HTTPStatus.UNAUTHORIZED
    title = "Authentication failed"

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail

    @property
    def headers(self) -> dict[str, str]:
        if self.status == HTTPStatus.UNAUTHORIZED:
            return {"WWW-Authenticate": "Bearer"}
        return {}


class InvalidTokenError(AuthError):
    status = HTTPStatus.UNAUTHORIZED
    title = "Invalid or missing token"


class ForbiddenError(AuthError):
    status = HTTPStatus.FORBIDDEN
    title = "Insufficient permissions"


class KeysUnavailableError(AuthError):
    status = HTTPStatus.SERVICE_UNAVAILABLE
    title = "Signing keys unavailable"
