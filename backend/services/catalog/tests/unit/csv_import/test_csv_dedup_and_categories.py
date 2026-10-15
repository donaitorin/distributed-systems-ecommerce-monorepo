from uuid import uuid4

import pytest

from catalog.domain.csv_import import CategoryIndex, category_key
from catalog.domain.csv_import.dedup import Occurrence, resolve_repeats
from catalog.domain.product import Category

A = b"a" * 16
B = b"b" * 16


def test_a_repeat_identical_to_the_winner_is_a_silent_duplicate() -> None:
    resolution = resolve_repeats("S-1", [Occurrence(2, A)], Occurrence(5, A))

    assert (resolution.duplicates, resolution.superseded, resolution.warnings) == (1, 0, ())


def test_a_repeat_different_from_the_winner_is_superseded_with_a_warning() -> None:
    resolution = resolve_repeats("S-1", [Occurrence(2, B)], Occurrence(5, A))

    assert (resolution.duplicates, resolution.superseded) == (0, 1)
    warning = resolution.warnings[0]
    assert (warning.row, warning.column, warning.value, warning.code) == (
        2,
        "sku",
        "S-1",
        "superseded",
    )
    assert warning.reason == "replaced by row 5, the last row with this SKU"


def test_the_order_of_the_earlier_rows_does_not_change_the_outcome() -> None:
    winner = Occurrence(9, A)
    forward = resolve_repeats("S-1", [Occurrence(2, A), Occurrence(4, B), Occurrence(6, A)], winner)
    backward = resolve_repeats(
        "S-1", [Occurrence(6, A), Occurrence(4, B), Occurrence(2, A)], winner
    )

    assert (forward.duplicates, forward.superseded) == (2, 1)
    assert (backward.duplicates, backward.superseded) == (2, 1)
    assert [item.row for item in forward.warnings] == [4]


def test_when_the_winner_is_invalid_every_earlier_row_is_superseded_by_it() -> None:
    resolution = resolve_repeats("S-1", [Occurrence(2, A), Occurrence(3, A)], Occurrence(6, None))

    assert (resolution.duplicates, resolution.superseded) == (0, 2)
    assert {item.code for item in resolution.warnings} == {"superseded_by_invalid"}
    assert resolution.warnings[0].reason == (
        "replaced by row 6, which has errors, so this SKU is not imported"
    )


def test_a_valid_occurrence_knows_it_is_valid() -> None:
    assert Occurrence(2, A).valid
    assert not Occurrence(2, None).valid


def build_index(*names: str) -> CategoryIndex:
    return CategoryIndex.of(Category(uuid4(), name, name.lower()) for name in names)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Electronics", "electronics"),
        ("  ELECTRONICS ", "electronics"),
        ("Home   &\tOffice", "home & office"),
        ("ÉCOLE", "école"),
        ("Straße", "strasse"),
    ],
)
def test_the_category_key_ignores_case_and_whitespace(raw: str, expected: str) -> None:
    assert category_key(raw) == expected


def test_resolve_finds_categories_regardless_of_case_and_spaces() -> None:
    index = build_index("Home & Office", "Books")

    assert index.resolve("  home &   OFFICE ") is not None
    assert index.resolve("books") is not None
    assert index.resolve("Boks") is None
    assert index.resolve("") is None


@pytest.mark.parametrize(
    ("raw", "suggestion"),
    [
        ("Electornics", "Electronics"),
        ("Home and Office", "Home & Office"),
        ("food beverage", "Food & Beverage"),
        ("Sport", "Sports"),
        ("Zzzzzz", None),
        ("", None),
    ],
)
def test_suggest_returns_the_closest_existing_name(raw: str, suggestion: str | None) -> None:
    index = build_index("Electronics", "Home & Office", "Food & Beverage", "Sports", "Books")

    assert index.suggest(raw) == suggestion


def test_an_empty_index_suggests_nothing() -> None:
    assert build_index().suggest("Anything") is None
