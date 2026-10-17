from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from payments_testing.data import START, SteppingClock

from payments.domain.payment import (
    CARD_DECLINED,
    ChargeRequest,
    Declined,
    Processing,
    RefundRequest,
    Succeeded,
)
from payments.infra.simulated import SimulatedPaymentProvider

DELAY = timedelta(seconds=90)


def request(card_last4: str) -> ChargeRequest:
    order_id = uuid4()
    return ChargeRequest(order_id, Decimal("10.00"), "USD", card_last4, str(order_id))


@pytest.fixture
def provider() -> SimulatedPaymentProvider:
    return SimulatedPaymentProvider(DELAY, SteppingClock())


@pytest.mark.parametrize("card", ["1111", "4242", "0001", "1234"])
async def test_every_card_but_the_special_endings_is_approved(
    provider: SimulatedPaymentProvider, card: str
) -> None:
    charge = request(card)

    outcome = await provider.charge(charge)

    assert outcome == Succeeded(f"sim_{charge.idempotency_key}")


async def test_a_card_ending_0000_is_declined(provider: SimulatedPaymentProvider) -> None:
    assert await provider.charge(request("0000")) == Declined(CARD_DECLINED)


async def test_a_card_ending_9999_never_answers(provider: SimulatedPaymentProvider) -> None:
    charge = request("9999")

    assert await provider.charge(charge) == Processing(None)
    assert await provider.status_of(charge) == Processing(None)


async def test_a_card_ending_2222_is_pending_until_the_delay_and_then_approved(
    provider: SimulatedPaymentProvider,
) -> None:
    charge = request("2222")

    first = await provider.charge(charge)
    later = await provider.status_of(charge)

    assert first == Processing(START + DELAY)
    assert later == Succeeded(f"sim_{charge.idempotency_key}")


async def test_the_delay_is_whatever_the_provider_was_built_with() -> None:
    provider = SimulatedPaymentProvider(timedelta(seconds=1.5), SteppingClock())

    assert await provider.charge(request("2222")) == Processing(START + timedelta(seconds=1.5))


async def test_charging_twice_with_the_same_key_gives_the_same_answer(
    provider: SimulatedPaymentProvider,
) -> None:
    charge = request("1111")

    assert await provider.charge(charge) == await provider.charge(charge)


async def test_refunds_are_accepted(provider: SimulatedPaymentProvider) -> None:
    order_id = uuid4()

    await provider.refund(RefundRequest(order_id, Decimal("10.00"), "USD", f"refund-{order_id}"))
