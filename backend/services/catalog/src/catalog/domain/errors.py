from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Violation:
    location: str
    message: str
    code: str


class DomainError(Exception):
    pass


class ValidationFailedError(DomainError):
    def __init__(self, violations: list[Violation]) -> None:
        super().__init__("; ".join(f"{item.location}: {item.message}" for item in violations))
        self.violations = tuple(violations)
