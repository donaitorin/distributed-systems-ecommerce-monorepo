from typing import Protocol


class HasSku(Protocol):
    @property
    def sku(self) -> str: ...


def require_unique_skus[LineT: HasSku](lines: list[LineT]) -> list[LineT]:
    skus = [line.sku for line in lines]
    if len(set(skus)) != len(skus):
        raise ValueError("lines cannot repeat a sku")
    return lines
