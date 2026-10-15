import json
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from ecommerce_contracts import (
    IMPORT_REQUESTED,
    IMPORT_VALIDATION_REQUESTED,
    IMPORTS_TOPIC,
    Envelope,
    ImportRequestedV1,
    ImportValidationRequestedV1,
)

EXAMPLES = Path(__file__).parent / "examples"
IMPORT_ID = UUID("9a1c1f0e-3a55-4a7c-b0b9-9d0f52f6a001")
DIGEST = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def load(name: str) -> dict[str, object]:
    data: dict[str, object] = json.loads((EXAMPLES / name).read_text())
    return data


def test_the_topic_and_event_names_are_stable() -> None:
    assert IMPORTS_TOPIC == "imports.jobs"
    assert IMPORT_REQUESTED == "import.requested"
    assert IMPORT_VALIDATION_REQUESTED == "import.validation_requested"


def test_the_stored_import_requested_example_parses_and_round_trips() -> None:
    raw = load("import_requested_v1.json")

    envelope = Envelope[ImportRequestedV1].model_validate(raw)

    assert envelope.event_type == IMPORT_REQUESTED
    assert envelope.payload.import_id == IMPORT_ID
    assert envelope.payload.sha256 == DIGEST
    assert json.loads(envelope.model_dump_json(exclude_none=True)) == raw


def test_the_stored_validation_requested_example_parses_and_round_trips() -> None:
    raw = load("import_validation_requested_v1.json")

    envelope = Envelope[ImportValidationRequestedV1].model_validate(raw)

    assert envelope.event_type == IMPORT_VALIDATION_REQUESTED
    assert json.loads(envelope.model_dump_json(exclude_none=True)) == raw


def test_fields_added_later_are_ignored_by_old_consumers() -> None:
    raw = load("import_requested_v1.json")
    payload = raw["payload"]
    assert isinstance(payload, dict)
    payload["requested_by"] = "someone"

    envelope = Envelope[ImportRequestedV1].model_validate(raw)

    assert envelope.payload.import_id == IMPORT_ID


@pytest.mark.parametrize("missing", ["import_id", "object_key", "sha256"])
def test_every_payload_field_is_required(missing: str) -> None:
    raw = load("import_requested_v1.json")
    payload = raw["payload"]
    assert isinstance(payload, dict)
    del payload[missing]

    with pytest.raises(ValidationError):
        Envelope[ImportRequestedV1].model_validate(raw)


@pytest.mark.parametrize("digest", ["", "abc", "E3B0" + "0" * 60, "g" * 64, DIGEST + "0"])
def test_the_sha256_must_be_lowercase_hex_of_the_right_length(digest: str) -> None:
    with pytest.raises(ValidationError):
        ImportRequestedV1(import_id=IMPORT_ID, object_key="imports/x/source.csv", sha256=digest)


def test_an_empty_object_key_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ImportValidationRequestedV1(import_id=IMPORT_ID, object_key="", sha256=DIGEST)
