from uuid import UUID

import pytest

from catalog.application import correlation
from catalog.application.correlation import current_correlation_id

REQUEST_ID = "6f1d7c2e-4b8a-4e0b-9d35-2a7c9e1b5f40"


def test_the_request_id_becomes_the_correlation_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(correlation, "get_request_id", lambda: REQUEST_ID)

    assert current_correlation_id() == UUID(REQUEST_ID)


@pytest.mark.parametrize("request_id", [None, "", "not-a-uuid"])
def test_a_missing_or_malformed_request_id_gets_a_fresh_correlation_id(
    monkeypatch: pytest.MonkeyPatch, request_id: str | None
) -> None:
    monkeypatch.setattr(correlation, "get_request_id", lambda: request_id)

    first, second = current_correlation_id(), current_correlation_id()

    assert first != second
