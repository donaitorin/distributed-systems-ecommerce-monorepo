import re
from dataclasses import dataclass

_ENTITY_TAG = re.compile(r'^(?:W/)?"(\d+)"$')


@dataclass(frozen=True, slots=True)
class VersionPrecondition:
    any_version: bool = False
    versions: frozenset[int] = frozenset()

    def satisfied_by(self, version: int) -> bool:
        return self.any_version or version in self.versions

    @classmethod
    def parse(cls, header_value: str) -> "VersionPrecondition":
        value = header_value.strip()
        if value == "*":
            return cls(any_version=True)
        versions: set[int] = set()
        for candidate in value.split(","):
            match = _ENTITY_TAG.match(candidate.strip())
            if match:
                versions.add(int(match.group(1)))
        return cls(versions=frozenset(versions))


def format_entity_tag(version: int) -> str:
    return f'"{version}"'
