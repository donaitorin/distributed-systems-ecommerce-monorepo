from catalog.domain.errors import DomainError


class ProductNotFoundError(DomainError):
    def __init__(self, sku: str) -> None:
        super().__init__(f"product {sku} not found")
        self.sku = sku


class DuplicateSkuError(DomainError):
    def __init__(self, sku: str) -> None:
        super().__init__(f"sku {sku} already exists")
        self.sku = sku


class UnknownCategoryError(DomainError):
    pass


class DuplicateCategoryError(DomainError):
    def __init__(self, name: str) -> None:
        super().__init__(f"category {name} already exists")
        self.name = name


class PreconditionFailedError(DomainError):
    def __init__(self, sku: str) -> None:
        super().__init__(f"product {sku} was modified")
        self.sku = sku


class SearchTimeoutError(DomainError):
    def __init__(self, timeout_ms: int) -> None:
        super().__init__(f"search exceeded {timeout_ms} ms")
        self.timeout_ms = timeout_ms


class UploadTooLargeError(DomainError):
    def __init__(self, limit_bytes: int) -> None:
        super().__init__(f"upload exceeds {limit_bytes} bytes")
        self.limit_bytes = limit_bytes


class UnsupportedMediaError(DomainError):
    pass


class InvalidUploadError(DomainError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class ProductImageNotFoundError(DomainError):
    def __init__(self, sku: str) -> None:
        super().__init__(f"product {sku} has no image")
        self.sku = sku


class ImportNotFoundError(DomainError):
    def __init__(self, import_id: object) -> None:
        super().__init__(f"import {import_id} not found")
        self.import_id = import_id


class ImportTooLargeError(DomainError):
    def __init__(self, limit_bytes: int) -> None:
        super().__init__(f"import file exceeds {limit_bytes} bytes")
        self.limit_bytes = limit_bytes


class ImportNotRevalidatableError(DomainError):
    def __init__(self, status: str, reason: str) -> None:
        super().__init__(reason)
        self.status = status
        self.reason = reason


class ImportNotConfirmableError(DomainError):
    def __init__(self, status: str, reason: str) -> None:
        super().__init__(reason)
        self.status = status
        self.reason = reason


class DuplicateImportError(DomainError):
    pass
