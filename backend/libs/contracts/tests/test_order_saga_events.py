import json
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError

from ecommerce_contracts import (
    INVENTORY_TOPIC,
    ORDER_CANCELLED,
    ORDER_CONFIRMED,
    ORDER_CREATED,
    ORDER_PAYMENT_REQUESTED,
    ORDERS_TOPIC,
    PAYMENT_FAILED,
    PAYMENT_REFUNDED,
    PAYMENT_SUCCEEDED,
    PAYMENTS_TOPIC,
    STOCK_RELEASED,
    STOCK_RESERVATION_FAILED,
    STOCK_RESERVED,
    Envelope,
    OrderCancelledV1,
    OrderConfirmedV1,
    OrderCreatedV1,
    OrderPaymentRequestedV1,
    PaymentFailedV1,
    PaymentRefundedV1,
    PaymentSucceededV1,
    StockReleasedV1,
    StockReservationFailedV1,
    StockReservedV1,
)

EXAMPLES = Path(__file__).parent / "examples"

CASES: list[tuple[str, str, type[BaseModel], str]] = [
    ("order_created_v1.json", ORDER_CREATED, OrderCreatedV1, "orders-service"),
    (
        "order_payment_requested_v1.json",
        ORDER_PAYMENT_REQUESTED,
        OrderPaymentRequestedV1,
        "orders-service",
    ),
    ("order_confirmed_v1.json", ORDER_CONFIRMED, OrderConfirmedV1, "orders-service"),
    ("order_cancelled_v1.json", ORDER_CANCELLED, OrderCancelledV1, "orders-service"),
    ("stock_reserved_v1.json", STOCK_RESERVED, StockReservedV1, "catalog-service"),
    (
        "stock_reservation_failed_v1.json",
        STOCK_RESERVATION_FAILED,
        StockReservationFailedV1,
        "catalog-service",
    ),
    ("stock_released_v1.json", STOCK_RELEASED, StockReleasedV1, "catalog-service"),
    ("payment_succeeded_v1.json", PAYMENT_SUCCEEDED, PaymentSucceededV1, "payments-service"),
    ("payment_failed_v1.json", PAYMENT_FAILED, PaymentFailedV1, "payments-service"),
    ("payment_refunded_v1.json", PAYMENT_REFUNDED, PaymentRefundedV1, "payments-service"),
]

REQUIRED_FIELDS = {
    "order_created_v1.json": ["order_id", "customer_id", "lines", "occurred_at"],
    "order_payment_requested_v1.json": [
        "order_id",
        "customer_id",
        "amount",
        "currency",
        "card_last4",
        "occurred_at",
    ],
    "order_confirmed_v1.json": [
        "order_id",
        "customer_id",
        "lines",
        "total",
        "currency",
        "occurred_at",
    ],
    "order_cancelled_v1.json": ["order_id", "customer_id", "reason", "occurred_at"],
    "stock_reserved_v1.json": ["order_id", "lines", "occurred_at"],
    "stock_reservation_failed_v1.json": ["order_id", "reason", "occurred_at"],
    "stock_released_v1.json": ["order_id", "lines", "occurred_at"],
    "payment_succeeded_v1.json": ["order_id", "payment_id", "amount", "currency", "occurred_at"],
    "payment_failed_v1.json": ["order_id", "payment_id", "reason", "occurred_at"],
    "payment_refunded_v1.json": [
        "order_id",
        "payment_id",
        "amount",
        "currency",
        "reason",
        "occurred_at",
    ],
}


def load(name: str) -> dict[str, object]:
    data: dict[str, object] = json.loads((EXAMPLES / name).read_text())
    return data


def payload_of(raw: dict[str, object]) -> dict[str, object]:
    payload = raw["payload"]
    assert isinstance(payload, dict)
    return payload


def parse(model: type[BaseModel], raw: dict[str, object]) -> Envelope[BaseModel]:
    return Envelope[model].model_validate(raw)  # type: ignore[valid-type]


def test_the_topic_names_are_stable() -> None:
    assert (ORDERS_TOPIC, INVENTORY_TOPIC, PAYMENTS_TOPIC) == (
        "orders.events",
        "inventory.events",
        "payments.events",
    )


@pytest.mark.parametrize(("name", "event_type", "model", "producer"), CASES)
def test_every_stored_example_parses_and_round_trips(
    name: str, event_type: str, model: type[BaseModel], producer: str
) -> None:
    raw = load(name)

    envelope = parse(model, raw)

    assert envelope.event_type == event_type
    assert envelope.event_version == 1
    assert envelope.producer == producer
    assert json.loads(envelope.model_dump_json(exclude_none=True)) == raw


@pytest.mark.parametrize(("name", "event_type", "model", "producer"), CASES)
def test_fields_added_later_are_ignored_by_old_consumers(
    name: str, event_type: str, model: type[BaseModel], producer: str
) -> None:
    raw = load(name)
    payload_of(raw)["new_optional_field"] = "x"

    assert parse(model, raw).event_type == event_type


@pytest.mark.parametrize(
    ("name", "missing"),
    [(name, field) for name, fields in REQUIRED_FIELDS.items() for field in fields],
)
def test_every_required_field_is_enforced(name: str, missing: str) -> None:
    case = next(item for item in CASES if item[0] == name)
    raw = load(name)
    del payload_of(raw)[missing]

    with pytest.raises(ValidationError):
        parse(case[2], raw)


@pytest.mark.parametrize(
    ("name", "field", "value"),
    [
        ("order_created_v1.json", "lines", []),
        ("order_confirmed_v1.json", "total", "-0.01"),
        ("order_confirmed_v1.json", "total", "1.005"),
        ("order_payment_requested_v1.json", "amount", "0.00"),
        ("order_payment_requested_v1.json", "currency", "usd"),
        ("order_payment_requested_v1.json", "card_last4", "11111"),
        ("order_payment_requested_v1.json", "card_last4", "4242424242421111"),
        ("order_payment_requested_v1.json", "card_last4", "abcd"),
        ("order_cancelled_v1.json", "reason", ""),
        ("stock_reserved_v1.json", "lines", []),
        ("stock_reservation_failed_v1.json", "available", -1),
        ("stock_released_v1.json", "lines", []),
        ("payment_succeeded_v1.json", "amount", "0"),
        ("payment_refunded_v1.json", "amount", "-5.00"),
    ],
)
def test_invalid_values_are_rejected(name: str, field: str, value: object) -> None:
    case = next(item for item in CASES if item[0] == name)
    raw = load(name)
    payload_of(raw)[field] = value

    with pytest.raises(ValidationError):
        parse(case[2], raw)


@pytest.mark.parametrize("name", ["order_created_v1.json", "order_confirmed_v1.json"])
def test_an_order_cannot_repeat_a_sku(name: str) -> None:
    case = next(item for item in CASES if item[0] == name)
    raw = load(name)
    lines = payload_of(raw)["lines"]
    assert isinstance(lines, list)
    lines.append(dict(lines[0]))

    with pytest.raises(ValidationError, match="repeat a sku"):
        parse(case[2], raw)


def test_a_reservation_cannot_repeat_a_sku() -> None:
    raw = load("stock_reserved_v1.json")
    lines = payload_of(raw)["lines"]
    assert isinstance(lines, list)
    lines.append(dict(lines[0]))

    with pytest.raises(ValidationError, match="repeat a sku"):
        parse(StockReservedV1, raw)


def test_money_travels_as_strings_so_no_precision_is_lost() -> None:
    envelope = parse(OrderPaymentRequestedV1, load("order_payment_requested_v1.json"))

    dumped = json.loads(envelope.model_dump_json())

    assert dumped["payload"]["amount"] == "92.30"
    assert envelope.payload.amount == Decimal("92.30")  # type: ignore[attr-defined]


def test_a_failure_may_carry_the_authoritative_price() -> None:
    raw = load("stock_reservation_failed_v1.json")
    payload = payload_of(raw)
    payload["reason"] = "price_changed"
    payload["current_price"] = "41.00"

    envelope = parse(StockReservationFailedV1, raw)

    assert envelope.payload.current_price == Decimal("41.00")  # type: ignore[attr-defined]


def test_timestamps_must_carry_a_timezone() -> None:
    raw = load("order_cancelled_v1.json")
    payload_of(raw)["occurred_at"] = "2026-10-17T09:15:00"

    with pytest.raises(ValidationError):
        parse(OrderCancelledV1, raw)
