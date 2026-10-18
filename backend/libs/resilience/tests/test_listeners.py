import logging

import pytest

from ecommerce_resilience import CallOutcome, CircuitState, LoggingListener


def test_a_state_change_is_logged_with_the_circuit_name(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)

    LoggingListener().state_changed("catalog", CircuitState.CLOSED, CircuitState.OPEN)

    [record] = caplog.records
    assert record.__dict__["circuit"] == "catalog"
    assert (record.__dict__["from_state"], record.__dict__["to_state"]) == ("closed", "open")


def test_individual_calls_are_not_logged(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)

    LoggingListener().call_finished("catalog", CallOutcome.SUCCESS)

    assert caplog.records == []
