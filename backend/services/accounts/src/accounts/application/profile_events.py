import logging
from collections.abc import Callable
from datetime import datetime

from accounts.application.clock import utc_now
from accounts.application.ports import ProfileRepository
from accounts.domain.profile import normalize_email
from ecommerce_contracts import Envelope, UserRegisteredV1, UserRoleChangedV1

logger = logging.getLogger(__name__)


class ProfileEvents:
    def __init__(self, clock: Callable[[], datetime] = utc_now) -> None:
        self._clock = clock

    async def registered(
        self, envelope: Envelope[UserRegisteredV1], profiles: ProfileRepository
    ) -> None:
        payload = envelope.payload
        await profiles.apply_registered(
            payload.user_id,
            normalize_email(payload.email),
            payload.role,
            payload.registered_at,
            self._clock(),
        )
        logger.info(
            "user registered event applied",
            extra={
                "event_id": str(envelope.event_id),
                "correlation_id": str(envelope.correlation_id),
                "user_id": str(payload.user_id),
            },
        )

    async def role_changed(
        self, envelope: Envelope[UserRoleChangedV1], profiles: ProfileRepository
    ) -> None:
        payload = envelope.payload
        await profiles.apply_role_change(
            payload.user_id, payload.new_role, payload.changed_at, self._clock()
        )
        logger.info(
            "user role changed event applied",
            extra={
                "event_id": str(envelope.event_id),
                "correlation_id": str(envelope.correlation_id),
                "user_id": str(payload.user_id),
            },
        )
