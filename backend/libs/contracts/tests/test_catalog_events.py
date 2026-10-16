import json
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from ecommerce_contracts import (
    CATALOG_TOPIC,
    PRODUCT_DELETED,
    PRODUCT_UPDATED,
    Envelope,
    ProductDeletedV1,
    ProductUpdatedV1,
)

EXAMPLES = Path(__file__).parent / "examples"


def load(name: str) -> dict[str, object]:
    data: dict[str, object] = json.loads((EXAMPLES / name).read_text())
    return data


def payload_of(raw: dict[str, object]) -> dict[str, object]:
    payload = raw["payload"]
    assert isinstance(payload, dict)
    return payload


def test_the_topic_and_event_names_are_stable() -> None:
    assert CATALOG_TOPIC == "catalog.events"
    assert PRODUCT_UPDATED == "product.updated"
    assert PRODUCT_DELETED == "product.deleted"


def test_the_stored_product_updated_example_parses_and_round_trips() -> None:
    raw = load("product_updated_v1.json")

    envelope = Envelope[ProductUpdatedV1].model_validate(raw)

    assert envelope.event_type == PRODUCT_UPDATED
    assert envelope.payload.sku == "RS-001"
    assert envelope.payload.price == Decimal("39.90")
    assert envelope.payload.version == 4
    assert json.loads(envelope.model_dump_json(exclude_none=True)) == raw


def test_the_stored_product_deleted_example_parses_and_round_trips() -> None:
    raw = load("product_deleted_v1.json")

    envelope = Envelope[ProductDeletedV1].model_validate(raw)

    assert envelope.event_type == PRODUCT_DELETED
    assert (envelope.payload.sku, envelope.payload.version) == ("RS-001", 5)
    assert json.loads(envelope.model_dump_json(exclude_none=True)) == raw


def test_a_product_without_an_image_omits_the_image_key() -> None:
    raw = load("product_updated_v1.json")
    del payload_of(raw)["image_key"]

    assert Envelope[ProductUpdatedV1].model_validate(raw).payload.image_key is None


def test_the_price_travels_as_a_string_so_no_precision_is_lost() -> None:
    envelope = Envelope[ProductUpdatedV1].model_validate(load("product_updated_v1.json"))

    dumped = json.loads(envelope.model_dump_json())

    assert dumped["payload"]["price"] == "39.90"


def test_fields_added_later_are_ignored_by_old_updated_consumers() -> None:
    raw = load("product_updated_v1.json")
    payload_of(raw)["new_optional_field"] = "x"

    assert Envelope[ProductUpdatedV1].model_validate(raw).payload.sku == "RS-001"


def test_fields_added_later_are_ignored_by_old_deleted_consumers() -> None:
    raw = load("product_deleted_v1.json")
    payload_of(raw)["new_optional_field"] = "x"

    assert Envelope[ProductDeletedV1].model_validate(raw).payload.sku == "RS-001"


@pytest.mark.parametrize("missing", ["sku", "name", "price", "stock", "version", "occurred_at"])
def test_every_product_updated_field_but_the_image_is_required(missing: str) -> None:
    raw = load("product_updated_v1.json")
    del payload_of(raw)[missing]

    with pytest.raises(ValidationError):
        Envelope[ProductUpdatedV1].model_validate(raw)


@pytest.mark.parametrize("missing", ["sku", "version", "occurred_at"])
def test_every_product_deleted_field_is_required(missing: str) -> None:
    raw = load("product_deleted_v1.json")
    del payload_of(raw)[missing]

    with pytest.raises(ValidationError):
        Envelope[ProductDeletedV1].model_validate(raw)


@pytest.mark.parametrize(
    ("field", "value"),
    [("price", "-1.00"), ("price", "1.005"), ("stock", -1), ("version", 0)],
)
def test_invalid_values_are_rejected(field: str, value: object) -> None:
    raw = load("product_updated_v1.json")
    payload_of(raw)[field] = value

    with pytest.raises(ValidationError):
        Envelope[ProductUpdatedV1].model_validate(raw)


def test_timestamps_must_carry_a_timezone() -> None:
    raw = load("product_deleted_v1.json")
    payload_of(raw)["occurred_at"] = "2026-10-16T11:00:00"

    with pytest.raises(ValidationError):
        Envelope[ProductDeletedV1].model_validate(raw)
