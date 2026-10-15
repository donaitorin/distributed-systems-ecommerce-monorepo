from collections.abc import Sequence
from dataclasses import dataclass

from catalog.domain.csv_import import problems as codes
from catalog.domain.csv_import.problems import Problem, warning


@dataclass(frozen=True, slots=True)
class Occurrence:
    row: int
    digest: bytes | None

    @property
    def valid(self) -> bool:
        return self.digest is not None


@dataclass(frozen=True, slots=True)
class Resolution:
    duplicates: int
    superseded: int
    warnings: tuple[Problem, ...]


def resolve_repeats(sku: str, earlier: Sequence[Occurrence], winner: Occurrence) -> Resolution:
    duplicates = 0
    notes: list[Problem] = []
    for occurrence in earlier:
        if winner.valid and occurrence.digest == winner.digest:
            duplicates += 1
        elif winner.valid:
            reason = f"replaced by row {winner.row}, the last row with this SKU"
            notes.append(warning(occurrence.row, "sku", sku, codes.SUPERSEDED, reason))
        else:
            reason = f"replaced by row {winner.row}, which has errors, so this SKU is not imported"
            notes.append(warning(occurrence.row, "sku", sku, codes.SUPERSEDED_BY_INVALID, reason))
    return Resolution(duplicates, len(notes), tuple(notes))
