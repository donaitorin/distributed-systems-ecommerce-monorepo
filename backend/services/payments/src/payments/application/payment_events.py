from datetime import datetime

from ecommerce_contracts import (
    PAYMENT_FAILED,
    PAYMENT_REFUNDED,
    PAYMENT_SUCCEEDED,
    PAYMENTS_TOPIC,
    PaymentFailedV1,
    PaymentRefundedV1,
    PaymentSucceededV1,
)
from payments.application.ports import UnitOfWork
from payments.domain.payment import ORDER_CANCELLED_REFUND, Payment


async def publish_succeeded(uow: UnitOfWork, payment: Payment, now: datetime) -> None:
    await uow.events.add(
        topic=PAYMENTS_TOPIC,
        key=str(payment.order_id),
        event_type=PAYMENT_SUCCEEDED,
        payload=PaymentSucceededV1(
            order_id=payment.order_id,
            payment_id=payment.id,
            amount=payment.amount,
            currency=payment.currency,
            occurred_at=now,
        ),
        correlation_id=payment.correlation_id,
    )


async def publish_failed(uow: UnitOfWork, payment: Payment, reason: str, now: datetime) -> None:
    await uow.events.add(
        topic=PAYMENTS_TOPIC,
        key=str(payment.order_id),
        event_type=PAYMENT_FAILED,
        payload=PaymentFailedV1(
            order_id=payment.order_id, payment_id=payment.id, reason=reason, occurred_at=now
        ),
        correlation_id=payment.correlation_id,
    )


async def publish_refunded(uow: UnitOfWork, payment: Payment, now: datetime) -> None:
    await uow.events.add(
        topic=PAYMENTS_TOPIC,
        key=str(payment.order_id),
        event_type=PAYMENT_REFUNDED,
        payload=PaymentRefundedV1(
            order_id=payment.order_id,
            payment_id=payment.id,
            amount=payment.amount,
            currency=payment.currency,
            reason=ORDER_CANCELLED_REFUND,
            occurred_at=now,
        ),
        correlation_id=payment.correlation_id,
    )
