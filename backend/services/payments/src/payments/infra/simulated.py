from collections.abc import Callable
from datetime import datetime, timedelta

from payments.application.clock import utc_now
from payments.domain.payment import (
    CARD_DECLINED,
    ChargeOutcome,
    ChargeRequest,
    Declined,
    Processing,
    RefundRequest,
    Succeeded,
)

DECLINED_ENDING = "0000"
NEVER_ANSWERS_ENDING = "9999"
LATE_ENDING = "2222"


class SimulatedPaymentProvider:
    def __init__(
        self, late_approval_delay: timedelta, clock: Callable[[], datetime] = utc_now
    ) -> None:
        self._late_approval_delay = late_approval_delay
        self._clock = clock

    async def charge(self, request: ChargeRequest) -> ChargeOutcome:
        if request.card_last4 == LATE_ENDING:
            return Processing(self._clock() + self._late_approval_delay)
        return self._outcome(request)

    async def status_of(self, request: ChargeRequest) -> ChargeOutcome:
        return self._outcome(request)

    async def refund(self, request: RefundRequest) -> None:
        return None

    def _outcome(self, request: ChargeRequest) -> ChargeOutcome:
        if request.card_last4 == DECLINED_ENDING:
            return Declined(CARD_DECLINED)
        if request.card_last4 == NEVER_ANSWERS_ENDING:
            return Processing(None)
        return Succeeded(f"sim_{request.idempotency_key}")
