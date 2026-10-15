import json
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from ecommerce_contracts import (
    AUTH_TOPIC,
    USER_REGISTERED,
    USER_ROLE_CHANGED,
    Envelope,
    UserRegisteredV1,
    UserRoleChangedV1,
)

EXAMPLES = Path(__file__).parent / "examples"
USER_ID = UUID("3f2b8c1e-6d4a-4f7e-8a21-0b9c5d7e1a02")


def load(name: str) -> dict[str, object]:
    data: dict[str, object] = json.loads((EXAMPLES / name).read_text())
    return data


def payload_of(raw: dict[str, object]) -> dict[str, object]:
    payload = raw["payload"]
    assert isinstance(payload, dict)
    return payload


def test_the_topic_and_event_names_are_stable() -> None:
    assert AUTH_TOPIC == "auth.events"
    assert USER_REGISTERED == "user.registered"
    assert USER_ROLE_CHANGED == "user.role_changed"


def test_the_stored_user_registered_example_parses_and_round_trips() -> None:
    raw = load("user_registered_v1.json")

    envelope = Envelope[UserRegisteredV1].model_validate(raw)

    assert envelope.event_type == USER_REGISTERED
    assert envelope.payload.user_id == USER_ID
    assert envelope.payload.email == "ada@example.com"
    assert json.loads(envelope.model_dump_json(exclude_none=True)) == raw


def test_the_stored_role_changed_example_parses_and_round_trips() -> None:
    raw = load("user_role_changed_v1.json")

    envelope = Envelope[UserRoleChangedV1].model_validate(raw)

    assert envelope.event_type == USER_ROLE_CHANGED
    assert (envelope.payload.old_role, envelope.payload.new_role) == ("customer", "admin")
    assert json.loads(envelope.model_dump_json(exclude_none=True)) == raw


def test_fields_added_later_are_ignored_by_old_registered_consumers() -> None:
    raw = load("user_registered_v1.json")
    payload_of(raw)["new_optional_field"] = "x"

    assert Envelope[UserRegisteredV1].model_validate(raw).payload.user_id == USER_ID


def test_fields_added_later_are_ignored_by_old_role_changed_consumers() -> None:
    raw = load("user_role_changed_v1.json")
    payload_of(raw)["new_optional_field"] = "x"

    assert Envelope[UserRoleChangedV1].model_validate(raw).payload.user_id == USER_ID


@pytest.mark.parametrize("missing", ["user_id", "email", "role", "registered_at"])
def test_every_user_registered_field_is_required(missing: str) -> None:
    raw = load("user_registered_v1.json")
    del payload_of(raw)[missing]

    with pytest.raises(ValidationError):
        Envelope[UserRegisteredV1].model_validate(raw)


@pytest.mark.parametrize("missing", ["user_id", "old_role", "new_role", "changed_by", "changed_at"])
def test_every_role_changed_field_is_required(missing: str) -> None:
    raw = load("user_role_changed_v1.json")
    del payload_of(raw)[missing]

    with pytest.raises(ValidationError):
        Envelope[UserRoleChangedV1].model_validate(raw)


def test_the_role_is_a_free_string_so_a_new_role_does_not_break_consumers() -> None:
    raw = load("user_registered_v1.json")
    payload_of(raw)["role"] = "support_agent"

    assert Envelope[UserRegisteredV1].model_validate(raw).payload.role == "support_agent"


def test_timestamps_must_carry_a_timezone() -> None:
    raw = load("user_registered_v1.json")
    payload_of(raw)["registered_at"] = "2026-10-15T21:00:00"

    with pytest.raises(ValidationError):
        Envelope[UserRegisteredV1].model_validate(raw)
