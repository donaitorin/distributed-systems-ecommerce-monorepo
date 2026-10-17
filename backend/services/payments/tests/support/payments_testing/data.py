from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from ecommerce_contracts import (
    ORDER_CANCELLED,
    ORDER_PAYMENT_REQUESTED,
    ORDERS_TOPIC,
    Envelope,
    OrderCancelledV1,
    OrderPaymentRequestedV1,
)
from ecommerce_messaging import OutgoingMessage
from payments.application.errors import ProviderUnavailableError
from payments.application.ports import PaymentProvider
from payments.domain.payment import ChargeOutcome, ChargeRequest, RefundRequest

START = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)
CUSTOMER = UUID("11111111-1111-4111-8111-111111111111")
OTHER_CUSTOMER = UUID("22222222-2222-4222-8222-222222222222")
CARD_DIGITS = "4929123456781111"


class SteppingClock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float = 0) -> None:
        self.now += timedelta(seconds=seconds)


def payment_requested(
    order_id: UUID | None = None,
    card_last4: str = "1111",
    amount: str = "92.30",
    customer_id: UUID = CUSTOMER,
    correlation_id: UUID | None = None,
) -> Envelope[OrderPaymentRequestedV1]:
    return Envelope[OrderPaymentRequestedV1](
        event_type=ORDER_PAYMENT_REQUESTED,
        event_version=1,
        correlation_id=correlation_id or uuid4(),
        producer="orders-service",
        payload=OrderPaymentRequestedV1(
            order_id=order_id or uuid4(),
            customer_id=customer_id,
            amount=Decimal(amount),
            currency="USD",
            card_last4=card_last4,
            occurred_at=START,
        ),
    )


def order_cancelled(order_id: UUID, customer_id: UUID = CUSTOMER) -> Envelope[OrderCancelledV1]:
    return Envelope[OrderCancelledV1](
        event_type=ORDER_CANCELLED,
        event_version=1,
        correlation_id=uuid4(),
        producer="orders-service",
        payload=OrderCancelledV1(
            order_id=order_id, customer_id=customer_id, reason="saga_timeout", occurred_at=START
        ),
    )


def outgoing(
    envelope: Envelope[OrderPaymentRequestedV1] | Envelope[OrderCancelledV1],
) -> OutgoingMessage:
    return OutgoingMessage(
        ORDERS_TOPIC, str(envelope.payload.order_id), envelope.model_dump_json().encode()
    )


class RecordingProvider:
    def __init__(self, inner: PaymentProvider) -> None:
        self.inner = inner
        self.charges: list[ChargeRequest] = []
        self.checks: list[ChargeRequest] = []
        self.refunds: list[RefundRequest] = []
        self.fail_next_refunds = 0

    async def charge(self, request: ChargeRequest) -> ChargeOutcome:
        self.charges.append(request)
        return await self.inner.charge(request)

    async def status_of(self, request: ChargeRequest) -> ChargeOutcome:
        self.checks.append(request)
        return await self.inner.status_of(request)

    async def refund(self, request: RefundRequest) -> None:
        self.refunds.append(request)
        if self.fail_next_refunds:
            self.fail_next_refunds -= 1
            raise ProviderUnavailableError("provider down")
        await self.inner.refund(request)
