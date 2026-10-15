import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from catalog.domain.csv_import import problems as codes
from catalog.domain.csv_import.problems import Problem, Severity, error, warning

DECIMAL_PATTERN: Final = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)")
INTEGER_PATTERN: Final = re.compile(r"[+-]?[0-9]+")
CURRENCY_SYMBOL: Final = "$"


@dataclass(frozen=True, slots=True)
class Parsed[T]:
    value: T | None
    problems: tuple[Problem, ...] = ()

    @property
    def failed(self) -> bool:
        return any(item.severity is Severity.ERROR for item in self.problems)


def parse_price(raw: str, row: int) -> Parsed[Decimal]:
    text = raw.strip()
    notes: tuple[Problem, ...] = ()
    if not text:
        return Parsed(None, (error(row, "price", raw, codes.REQUIRED, "price is required"),))
    if text.startswith(CURRENCY_SYMBOL):
        text = text[len(CURRENCY_SYMBOL) :].strip()
        notes = (
            warning(
                row,
                "price",
                raw,
                codes.PRICE_NORMALIZED,
                f"currency symbol removed, read as {text}",
            ),
        )
    if not DECIMAL_PATTERN.fullmatch(text):
        return Parsed(
            None,
            (
                error(
                    row,
                    "price",
                    raw,
                    codes.NOT_A_NUMBER,
                    "price must be a plain number such as 29.99",
                ),
            ),
        )
    return Parsed(Decimal(text), notes)


def parse_stock(raw: str, row: int) -> Parsed[int]:
    text = raw.strip()
    if not text:
        return Parsed(None, (error(row, "stock", raw, codes.REQUIRED, "stock is required"),))
    if not INTEGER_PATTERN.fullmatch(text):
        return Parsed(
            None,
            (error(row, "stock", raw, codes.NOT_AN_INTEGER, "stock must be a whole number"),),
        )
    try:
        return Parsed(int(text))
    except ValueError:
        return Parsed(
            None,
            (error(row, "stock", raw, codes.NOT_AN_INTEGER, "stock has too many digits"),),
        )


def parse_weight(raw: str, row: int) -> Parsed[Decimal | None]:
    text = raw.strip()
    if not text:
        return Parsed(None)
    if not DECIMAL_PATTERN.fullmatch(text):
        return Parsed(
            None,
            (
                error(
                    row,
                    "weight_kg",
                    raw,
                    codes.NOT_A_NUMBER,
                    "weight_kg must be a plain number such as 0.35, or empty",
                ),
            ),
        )
    return Parsed(Decimal(text))
