from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from payments_testing.data import (
    CUSTOMER,
    RecordingProvider,
    SteppingClock,
    order_cancelled,
    payment_requested,
)

from ecommerce_contracts import (
    PAYMENT_FAILED,
    PAYMENT_REFUNDED,
    PAYMENT_SUCCEEDED,
    PAYMENTS_TOPIC,
    PaymentFailedV1,
    PaymentRefundedV1,
    PaymentSucceededV1,
)
from payments.application.errors import ProviderUnavailableError
from payments.application.processor import PaymentProcessor
from payments.domain.payment import ChargeOutcome, ChargeRequest, PaymentStatus, Succeeded
from payments.infra.memory import InMemoryStore, InMemoryUnitOfWork
from payments.infra.simulated import SimulatedPaymentProvider

DELAY = timedelta(seconds=90)


@pytest.fixture
def provider(clock: SteppingClock) -> RecordingProvider:
    return RecordingProvider(SimulatedPaymentProvider(DELAY, clock))


@pytest.fixture
def processor(
    store: InMemoryStore, provider: RecordingProvider, clock: SteppingClock
) -> PaymentProcessor:
    return PaymentProcessor(lambda: InMemoryUnitOfWork(store), provider, clock)


async def charge(processor: PaymentProcessor, card: str, amount: str = "92.30") -> UUID:
    envelope = payment_requested(card_last4=card, amount=amount)
    await processor.charge_requested(envelope.payload, envelope.correlation_id)
    return envelope.payload.order_id


def status_of(store: InMemoryStore, order_id: UUID) -> PaymentStatus:
    return store.payments[order_id].status


def events(store: InMemoryStore, order_id: UUID) -> list[str]:
    return [entry.event_type for entry in store.outbox if entry.key == str(order_id)]


async def test_an_approved_card_succeeds_and_announces_it(
    processor: PaymentProcessor, store: InMemoryStore
) -> None:
    order_id = await charge(processor, "1111")

    payment = store.payments[order_id]
    assert payment.status is PaymentStatus.SUCCEEDED
    assert (str(payment.amount), payment.currency, payment.card_last4) == ("92.30", "USD", "1111")
    [entry] = store.outbox
    assert (entry.topic, entry.event_type, entry.key) == (
        PAYMENTS_TOPIC,
        PAYMENT_SUCCEEDED,
        str(order_id),
    )
    assert isinstance(entry.payload, PaymentSucceededV1)
    assert (entry.payload.payment_id, str(entry.payload.amount)) == (payment.id, "92.30")
    assert entry.correlation_id == payment.correlation_id


async def test_a_declined_card_fails_with_the_reason_and_announces_it(
    processor: PaymentProcessor, store: InMemoryStore
) -> None:
    order_id = await charge(processor, "0000")

    payment = store.payments[order_id]
    assert (payment.status, payment.failure_reason) == (PaymentStatus.FAILED, "card_declined")
    [entry] = store.outbox
    assert entry.event_type == PAYMENT_FAILED
    assert isinstance(entry.payload, PaymentFailedV1)
    assert entry.payload.reason == "card_declined"


async def test_a_card_that_never_answers_stays_pending_forever(
    processor: PaymentProcessor,
    store: InMemoryStore,
    clock: SteppingClock,
    provider: RecordingProvider,
) -> None:
    order_id = await charge(processor, "9999")
    clock.advance(seconds=10**6)

    assert await processor.settle_due() == 0

    payment = store.payments[order_id]
    assert (payment.status, payment.check_after) == (PaymentStatus.PENDING, None)
    assert payment.submitted_at is not None
    assert store.outbox == []
    assert provider.checks == []


async def test_a_late_card_is_approved_only_after_the_delay(
    processor: PaymentProcessor,
    store: InMemoryStore,
    clock: SteppingClock,
    provider: RecordingProvider,
) -> None:
    order_id = await charge(processor, "2222")
    assert status_of(store, order_id) is PaymentStatus.PENDING
    clock.advance(seconds=89)
    assert await processor.settle_due() == 0

    clock.advance(seconds=1)
    assert await processor.settle_due() == 1

    assert status_of(store, order_id) is PaymentStatus.SUCCEEDED
    assert events(store, order_id) == [PAYMENT_SUCCEEDED]
    assert len(provider.checks) == 1
    assert await processor.settle_due() == 0


async def test_the_same_request_delivered_twice_charges_and_announces_once(
    processor: PaymentProcessor, store: InMemoryStore, provider: RecordingProvider
) -> None:
    envelope = payment_requested(card_last4="1111")

    await processor.charge_requested(envelope.payload, envelope.correlation_id)
    await processor.charge_requested(envelope.payload, envelope.correlation_id)

    assert len(provider.charges) == 1
    assert len(store.payments) == 1
    assert len(store.outbox) == 1
    assert provider.charges[0].idempotency_key == str(envelope.payload.order_id)


async def test_a_request_redelivered_while_a_late_charge_is_pending_does_not_charge_again(
    processor: PaymentProcessor, provider: RecordingProvider
) -> None:
    envelope = payment_requested(card_last4="2222")

    await processor.charge_requested(envelope.payload, envelope.correlation_id)
    await processor.charge_requested(envelope.payload, envelope.correlation_id)

    assert len(provider.charges) == 1


async def test_a_crash_between_saving_and_charging_is_repaired_by_the_redelivery(
    store: InMemoryStore, clock: SteppingClock
) -> None:
    class Flaky(RecordingProvider):
        async def charge(self, request: ChargeRequest) -> ChargeOutcome:
            self.charges.append(request)
            if len(self.charges) == 1:
                raise ProviderUnavailableError("timeout")
            return await self.inner.charge(request)

    flaky = Flaky(SimulatedPaymentProvider(DELAY, clock))
    processor = PaymentProcessor(lambda: InMemoryUnitOfWork(store), flaky, clock)
    envelope = payment_requested(card_last4="1111")

    with pytest.raises(ProviderUnavailableError):
        await processor.charge_requested(envelope.payload, envelope.correlation_id)
    assert store.payments[envelope.payload.order_id].status is PaymentStatus.PENDING
    await processor.charge_requested(envelope.payload, envelope.correlation_id)

    assert store.payments[envelope.payload.order_id].status is PaymentStatus.SUCCEEDED
    assert {call.idempotency_key for call in flaky.charges} == {str(envelope.payload.order_id)}
    assert len(store.outbox) == 1


async def test_a_late_success_after_the_order_was_cancelled_is_refunded(
    processor: PaymentProcessor,
    store: InMemoryStore,
    clock: SteppingClock,
    provider: RecordingProvider,
) -> None:
    order_id = await charge(processor, "2222")
    await processor.order_cancelled(order_id)
    assert status_of(store, order_id) is PaymentStatus.PENDING
    clock.advance(seconds=90)

    await processor.settle_due()

    payment = store.payments[order_id]
    assert (payment.status, payment.refunded_at) == (PaymentStatus.REFUNDED, clock.now)
    assert events(store, order_id) == [PAYMENT_SUCCEEDED, PAYMENT_REFUNDED]
    refunded = store.outbox[-1].payload
    assert isinstance(refunded, PaymentRefundedV1)
    assert (str(refunded.amount), refunded.reason) == ("92.30", "order_cancelled")
    [refund] = provider.refunds
    assert refund.idempotency_key == f"refund-{order_id}"


async def test_cancelling_after_the_payment_succeeded_refunds_it(
    processor: PaymentProcessor, store: InMemoryStore, provider: RecordingProvider
) -> None:
    order_id = await charge(processor, "1111")

    await processor.order_cancelled(order_id)

    assert status_of(store, order_id) is PaymentStatus.REFUNDED
    assert events(store, order_id) == [PAYMENT_SUCCEEDED, PAYMENT_REFUNDED]
    assert len(provider.refunds) == 1


async def test_cancelling_twice_refunds_once(
    processor: PaymentProcessor, store: InMemoryStore, provider: RecordingProvider
) -> None:
    order_id = await charge(processor, "1111")

    await processor.order_cancelled(order_id)
    await processor.order_cancelled(order_id)
    await processor.refund_due()

    assert len(provider.refunds) == 1
    assert events(store, order_id).count(PAYMENT_REFUNDED) == 1


@pytest.mark.parametrize("card", ["0000", "9999"])
async def test_cancelling_an_order_whose_payment_never_succeeded_refunds_nothing(
    processor: PaymentProcessor, store: InMemoryStore, provider: RecordingProvider, card: str
) -> None:
    order_id = await charge(processor, card)

    await processor.order_cancelled(order_id)

    assert provider.refunds == []
    assert PAYMENT_REFUNDED not in events(store, order_id)
    assert store.payments[order_id].order_cancelled


async def test_a_cancellation_for_an_unknown_order_is_ignored(
    processor: PaymentProcessor, store: InMemoryStore
) -> None:
    await processor.order_cancelled(order_cancelled(uuid4()).payload.order_id)

    assert not store.payments
    assert not store.outbox


async def test_a_refund_that_failed_is_retried_by_the_sweep_and_announced_once(
    processor: PaymentProcessor, store: InMemoryStore, provider: RecordingProvider
) -> None:
    order_id = await charge(processor, "1111")
    provider.fail_next_refunds = 1

    with pytest.raises(ProviderUnavailableError):
        await processor.order_cancelled(order_id)
    assert status_of(store, order_id) is PaymentStatus.SUCCEEDED
    assert await processor.refund_due() == 1
    assert await processor.refund_due() == 0

    assert status_of(store, order_id) is PaymentStatus.REFUNDED
    assert events(store, order_id).count(PAYMENT_REFUNDED) == 1
    assert {call.idempotency_key for call in provider.refunds} == {f"refund-{order_id}"}


async def test_a_late_result_for_a_payment_already_decided_changes_nothing(
    processor: PaymentProcessor, store: InMemoryStore
) -> None:
    order_id = await charge(processor, "0000")
    emitted = list(store.outbox)

    await processor.apply(order_id, Succeeded("late"))

    assert status_of(store, order_id) is PaymentStatus.FAILED
    assert store.outbox == emitted


async def test_the_customer_is_kept_for_ownership_checks(
    processor: PaymentProcessor, store: InMemoryStore
) -> None:
    order_id = await charge(processor, "1111")

    assert store.payments[order_id].customer_id == CUSTOMER
