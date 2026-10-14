import pytest

from catalog.domain.errors import ValidationFailedError
from catalog.domain.slug import build_category, normalize_category_name, slugify


@pytest.mark.parametrize(
    ("name", "slug"),
    [
        ("Electronics", "electronics"),
        ("Food & Beverage", "food-beverage"),
        ("Home & Office", "home-office"),
        ("  Pet   Supplies  ", "pet-supplies"),
        ("Café Münchën", "cafe-munchen"),
        ("100% Organic!", "100-organic"),
    ],
)
def test_slugify(name: str, slug: str) -> None:
    assert slugify(name) == slug


def test_names_are_trimmed_and_inner_whitespace_collapsed() -> None:
    assert normalize_category_name("  Pet \t  Supplies ") == "Pet Supplies"


def test_build_category_returns_name_and_slug() -> None:
    assert build_category("  Food &   Beverage ") == ("Food & Beverage", "food-beverage")


@pytest.mark.parametrize(
    ("raw", "code"),
    [("", "required"), ("   ", "required"), ("!!!", "invalid_name"), ("x" * 101, "too_long")],
)
def test_invalid_category_names(raw: str, code: str) -> None:
    with pytest.raises(ValidationFailedError) as raised:
        build_category(raw)

    assert [(item.location, item.code) for item in raised.value.violations] == [("name", code)]


def test_name_that_slugifies_to_nothing_is_rejected() -> None:
    with pytest.raises(ValidationFailedError):
        build_category("日本語")
