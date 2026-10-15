import difflib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Self
from uuid import UUID

from catalog.domain.product import Category

SUGGESTION_CUTOFF = 0.6


def category_key(name: str) -> str:
    return " ".join(name.split()).casefold()


@dataclass(frozen=True, slots=True)
class CategoryIndex:
    ids: Mapping[str, UUID]
    names: Mapping[str, str]

    @classmethod
    def of(cls, categories: Iterable[Category]) -> Self:
        listed = list(categories)
        return cls(
            ids={category_key(item.name): item.id for item in listed},
            names={category_key(item.name): item.name for item in listed},
        )

    def resolve(self, raw: str) -> UUID | None:
        return self.ids.get(category_key(raw))

    def suggest(self, raw: str) -> str | None:
        close = difflib.get_close_matches(
            category_key(raw), list(self.names), n=1, cutoff=SUGGESTION_CUTOFF
        )
        return self.names[close[0]] if close else None
