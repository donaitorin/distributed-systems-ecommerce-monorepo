from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from payments.application.ports import UnitOfWorkFactory
from payments.domain.payment import NewPayment, PaymentStatus

NOW = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)


def new_payment(order_id: UUID | None = None) -> NewPayment:
    return NewPayment(order_id or uuid4(), uuid4(), Decimal("92.30"), "USD", "1111", uuid4())


async def add(factory: UnitOfWorkFactory, payment: NewPayment) -> None:
    async with factory() as uow:
        await uow.payments.add(payment, NOW)
        await uow.commit()


async def test_an_added_payment_reads_back_with_exact_money(
    unit_of_work: UnitOfWorkFactory,
) -> None:
    payment = new_payment()
    async with unit_of_work() as uow:
        inserted = await uow.payments.add(payment, NOW)
        await uow.commit()

    async with unit_of_work() as uow:
        stored = await uow.payments.get_by_order(payment.order_id)

    assert inserted
    assert stored is not None
    assert (stored.status, str(stored.amount), stored.card_last4) == (
        PaymentStatus.PENDING,
        "92.30",
        "1111",
    )
    assert (stored.customer_id, stored.correlation_id) == (
        payment.customer_id,
        payment.correlation_id,
    )
    assert (stored.order_cancelled, stored.submitted_at, stored.check_after) == (False, None, None)
    assert stored.awaiting_provider


async def test_a_second_payment_for_the_same_order_is_ignored(
    unit_of_work: UnitOfWorkFactory,
) -> None:
    payment = new_payment()
    await add(unit_of_work, payment)

    async with unit_of_work() as uow:
        again = await uow.payments.add(new_payment(payment.order_id), NOW)

    assert again is False


async def test_an_unknown_order_has_no_payment(unit_of_work: UnitOfWorkFactory) -> None:
    async with unit_of_work() as uow:
        assert await uow.payments.get_by_order(uuid4()) is None
        assert await uow.payments.flag_order_cancelled(uuid4(), NOW) is None


async def test_uncommitted_work_is_discarded(unit_of_work: UnitOfWorkFactory) -> None:
    payment = new_payment()
    async with unit_of_work() as uow:
        await uow.payments.add(payment, NOW)

    async with unit_of_work() as uow:
        assert await uow.payments.get_by_order(payment.order_id) is None


async def test_submitting_records_the_time_and_when_to_check_again(
    unit_of_work: UnitOfWorkFactory,
) -> None:
    payment = new_payment()
    await add(unit_of_work, payment)
    later = NOW + timedelta(seconds=90)

    async with unit_of_work() as uow:
        assert await uow.payments.mark_submitted(payment.order_id, later, NOW)
        await uow.commit()

    async with unit_of_work() as uow:
        stored = await uow.payments.get_by_order(payment.order_id)
        due_early = await uow.payments.due_for_check(NOW, 10)
        due_later = await uow.payments.due_for_check(later, 10)
    assert stored is not None
    assert (stored.submitted_at, stored.check_after) == (NOW, later)
    assert not stored.awaiting_provider
    assert payment.order_id not in due_early
    assert payment.order_id in due_later


async def test_a_payment_that_never_answers_is_never_due(
    unit_of_work: UnitOfWorkFactory,
) -> None:
    payment = new_payment()
    await add(unit_of_work, payment)
    async with unit_of_work() as uow:
        await uow.payments.mark_submitted(payment.order_id, None, NOW)
        await uow.commit()

    async with unit_of_work() as uow:
        due = await uow.payments.due_for_check(NOW + timedelta(days=365), 100)

    assert payment.order_id not in due


async def test_success_and_failure_only_apply_to_pending_payments(
    unit_of_work: UnitOfWorkFactory,
) -> None:
    paid, declined = new_payment(), new_payment()
    await add(unit_of_work, paid)
    await add(unit_of_work, declined)

    async with unit_of_work() as uow:
        first = await uow.payments.succeed(paid.order_id, NOW)
        second = await uow.payments.succeed(paid.order_id, NOW)
        flipped = await uow.payments.fail(paid.order_id, "x", NOW)
        failed = await uow.payments.fail(declined.order_id, "card_declined", NOW)
        revived = await uow.payments.succeed(declined.order_id, NOW)
        await uow.commit()

    async with unit_of_work() as uow:
        stored_paid = await uow.payments.get_by_order(paid.order_id)
        stored_declined = await uow.payments.get_by_order(declined.order_id)
    assert (first, second, flipped, failed, revived) == (True, False, False, True, False)
    assert stored_paid is not None
    assert stored_paid.status is PaymentStatus.SUCCEEDED
    assert stored_declined is not None
    assert (stored_declined.status, stored_declined.failure_reason) == (
        PaymentStatus.FAILED,
        "card_declined",
    )


async def test_a_refund_needs_a_succeeded_payment_and_happens_once(
    unit_of_work: UnitOfWorkFactory,
) -> None:
    payment = new_payment()
    await add(unit_of_work, payment)

    async with unit_of_work() as uow:
        early = await uow.payments.refund(payment.order_id, NOW)
        await uow.payments.succeed(payment.order_id, NOW)
        first = await uow.payments.refund(payment.order_id, NOW)
        second = await uow.payments.refund(payment.order_id, NOW)
        await uow.commit()

    async with unit_of_work() as uow:
        stored = await uow.payments.get_by_order(payment.order_id)
    assert (early, first, second) == (False, True, False)
    assert stored is not None
    assert (stored.status, stored.refunded_at) == (PaymentStatus.REFUNDED, NOW)


async def test_refunds_are_due_for_succeeded_payments_of_cancelled_orders(
    unit_of_work: UnitOfWorkFactory,
) -> None:
    cancelled, kept, pending = new_payment(), new_payment(), new_payment()
    for payment in (cancelled, kept, pending):
        await add(unit_of_work, payment)
    async with unit_of_work() as uow:
        await uow.payments.succeed(cancelled.order_id, NOW)
        await uow.payments.succeed(kept.order_id, NOW)
        flagged = await uow.payments.flag_order_cancelled(cancelled.order_id, NOW)
        await uow.payments.flag_order_cancelled(pending.order_id, NOW)
        await uow.commit()

    async with unit_of_work() as uow:
        due = await uow.payments.refunds_due(100)

    assert flagged is not None
    assert (flagged.status, flagged.order_cancelled) == (PaymentStatus.SUCCEEDED, True)
    assert cancelled.order_id in due
    assert kept.order_id not in due
    assert pending.order_id not in due
