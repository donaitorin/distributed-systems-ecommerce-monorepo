import pytest

from catalog.domain.preconditions import VersionPrecondition, format_entity_tag


def test_entity_tag_is_the_quoted_version() -> None:
    assert format_entity_tag(3) == '"3"'


@pytest.mark.parametrize("header", ['"3"', 'W/"3"', ' "3" ', '"1", "3"', '"3","7"', "*"])
def test_matching_headers(header: str) -> None:
    assert VersionPrecondition.parse(header).satisfied_by(3)


@pytest.mark.parametrize("header", ['"2"', "3", "v3", '""', "", "garbage", '"3', '"-3"', '"3.0"'])
def test_non_matching_or_malformed_headers(header: str) -> None:
    assert not VersionPrecondition.parse(header).satisfied_by(3)


def test_wildcard_matches_any_version() -> None:
    precondition = VersionPrecondition.parse("*")

    assert precondition.any_version
    assert precondition.satisfied_by(1)
    assert precondition.satisfied_by(10_000)


def test_list_collects_every_valid_tag_and_ignores_the_rest() -> None:
    precondition = VersionPrecondition.parse('"1", junk, W/"4"')

    assert precondition.versions == frozenset({1, 4})
