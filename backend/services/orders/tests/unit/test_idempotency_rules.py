from dataclasses import replace
from decimal import Decimal

import pytest

from orders.domain.idempotency import fingerprint_of, is_valid_key
from orders.domain.order import LineRequest, OrderRequest, ShippingAddress

ADDRESS = ShippingAddress("Ada", "12 St", None, "London", None, "N1", "GB", None)


def request(*lines: LineRequest, card: str = "1111") -> OrderRequest:
    return OrderRequest(lines or (LineRequest("A-1", 1, Decimal("1.00")),), ADDRESS, card)


@pytest.mark.parametrize("key", ["abcdefgh", "a" * 128, "order-2026_10:17.001", "0" * 8])
def test_reasonable_keys_are_accepted(key: str) -> None:
    assert is_valid_key(key)


@pytest.mark.parametrize(
    "key", ["", "short", "a" * 129, "has space1", "ñandú-12345", "semi;colon1"]
)
def test_keys_that_are_short_long_or_exotic_are_refused(key: str) -> None:
    assert not is_valid_key(key)


def test_the_order_of_lines_does_not_change_the_fingerprint() -> None:
    first = LineRequest("A-1", 1, Decimal("1.00"))
    second = LineRequest("B-2", 2, Decimal("2.50"))

    assert fingerprint_of(request(first, second)) == fingerprint_of(request(second, first))


def test_how_a_price_is_written_does_not_change_the_fingerprint() -> None:
    plain = LineRequest("A-1", 1, Decimal("1.00"))
    short = LineRequest("A-1", 1, Decimal("1.0"))

    assert fingerprint_of(request(plain)) == fingerprint_of(request(short))


@pytest.mark.parametrize(
    "changed",
    [
        LineRequest("A-1", 2, Decimal("1.00")),
        LineRequest("A-1", 1, Decimal("1.01")),
        LineRequest("A-2", 1, Decimal("1.00")),
    ],
)
def test_any_change_to_a_line_changes_the_fingerprint(changed: LineRequest) -> None:
    assert fingerprint_of(request()) != fingerprint_of(request(changed))


def test_a_different_address_or_card_ending_changes_the_fingerprint() -> None:
    base = request()

    assert fingerprint_of(base) != fingerprint_of(request(card="0000"))
    other = replace(base, shipping_address=replace(ADDRESS, city="Leeds"))
    assert fingerprint_of(base) != fingerprint_of(other)
