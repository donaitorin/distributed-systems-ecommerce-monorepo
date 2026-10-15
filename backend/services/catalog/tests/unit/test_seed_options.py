import pytest

from catalog.tools.seed import DEFAULT_COUNT, MAX_COUNT, parse_count


def test_the_default_is_two_hundred_thousand_products() -> None:
    assert parse_count([]) == DEFAULT_COUNT == 200_000


def test_an_explicit_count_is_used() -> None:
    assert parse_count(["--count", "1500"]) == 1500


@pytest.mark.parametrize("count", ["0", "-5", str(MAX_COUNT + 1)])
def test_counts_outside_the_supported_range_are_rejected(count: str) -> None:
    with pytest.raises(SystemExit):
        parse_count(["--count", count])
