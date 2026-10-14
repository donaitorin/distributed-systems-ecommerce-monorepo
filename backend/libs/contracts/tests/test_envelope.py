import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel, ValidationError

from ecommerce_contracts import Envelope

EXAMPLES = Path(__file__).parent / "examples"


class SamplePayload(BaseModel):
    sample_id: str
    quantity: int
    note: str | None = None


def load_example(name: str) -> dict[str, object]:
    data: dict[str, object] = json.loads((EXAMPLES / name).read_text())
    return data


def build(**overrides: object) -> Envelope[SamplePayload]:
    fields: dict[str, object] = {
        "event_type": "sample.created",
        "event_version": 1,
        "correlation_id": uuid4(),
        "producer": "sample-service",
        "payload": SamplePayload(sample_id="s-1", quantity=1),
    } | overrides
    return Envelope[SamplePayload].model_validate(fields)


def test_stored_example_parses_and_round_trips() -> None:
    raw = load_example("sample_event_v1.json")

    envelope = Envelope[SamplePayload].model_validate(raw)

    assert envelope.event_id == UUID("7b0e1c52-3f0a-4a53-9a0b-2f4f6f0f6a11")
    assert envelope.payload == SamplePayload(sample_id="s-1", quantity=3)
    assert json.loads(envelope.model_dump_json(exclude_none=True)) == raw


def test_unknown_fields_are_ignored_for_forward_compatibility() -> None:
    raw = load_example("sample_event_v1.json")
    raw["added_later"] = "value"
    payload = raw["payload"]
    assert isinstance(payload, dict)
    payload["added_optional"] = True

    envelope = Envelope[SamplePayload].model_validate(raw)

    assert envelope.payload.note is None


def test_optional_payload_field_added_later_is_accepted() -> None:
    raw = load_example("sample_event_v1.json")
    payload = raw["payload"]
    assert isinstance(payload, dict)
    payload["note"] = "gift"

    envelope = Envelope[SamplePayload].model_validate(raw)

    assert envelope.payload.note == "gift"


@pytest.mark.parametrize(
    "missing",
    ["event_type", "event_version", "correlation_id", "producer", "payload"],
)
def test_missing_required_field_is_rejected(missing: str) -> None:
    raw = load_example("sample_event_v1.json")
    del raw[missing]

    with pytest.raises(ValidationError):
        Envelope[SamplePayload].model_validate(raw)


def test_defaults_generate_event_id_and_utc_timestamp() -> None:
    first, second = build(), build()

    assert first.event_id != second.event_id
    assert first.occurred_at.utcoffset() == timedelta(0)


def test_naive_timestamp_is_rejected() -> None:
    with pytest.raises(ValidationError):
        build(occurred_at=datetime(2026, 10, 12, 21, 0, 0))


def test_timestamp_is_normalized_to_utc() -> None:
    local = datetime(2026, 10, 12, 18, 0, tzinfo=timezone(timedelta(hours=-3)))

    envelope = build(occurred_at=local)

    assert envelope.occurred_at == datetime(2026, 10, 12, 21, 0, tzinfo=UTC)
    assert envelope.occurred_at.utcoffset() == timedelta(0)


@pytest.mark.parametrize("event_type", ["created", "Order.Created", "order..created", ""])
def test_malformed_event_type_is_rejected(event_type: str) -> None:
    with pytest.raises(ValidationError):
        build(event_type=event_type)


@pytest.mark.parametrize("version", [0, -1])
def test_event_version_must_be_positive(version: int) -> None:
    with pytest.raises(ValidationError):
        build(event_version=version)


def test_envelope_is_immutable() -> None:
    envelope = build()

    with pytest.raises(ValidationError):
        envelope.event_type = "sample.updated"  # type: ignore[misc]
