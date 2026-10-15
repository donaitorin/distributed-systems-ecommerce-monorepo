from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from ecommerce_contracts import (
    AUTH_TOPIC,
    USER_REGISTERED,
    USER_ROLE_CHANGED,
    Envelope,
    UserRegisteredV1,
    UserRoleChangedV1,
)
from ecommerce_messaging import IncomingMessage, OutgoingMessage


def registered_event(
    user_id: UUID,
    at: datetime,
    email: str = "ada@example.com",
    role: str = "customer",
    event_id: UUID | None = None,
) -> Envelope[UserRegisteredV1]:
    return Envelope[UserRegisteredV1](
        event_id=event_id or uuid4(),
        event_type=USER_REGISTERED,
        event_version=1,
        correlation_id=uuid4(),
        producer="auth-service",
        payload=UserRegisteredV1(user_id=user_id, email=email, role=role, registered_at=at),
    )


def role_changed_event(
    user_id: UUID,
    at: datetime,
    new_role: str = "admin",
    old_role: str = "customer",
    event_id: UUID | None = None,
) -> Envelope[UserRoleChangedV1]:
    return Envelope[UserRoleChangedV1](
        event_id=event_id or uuid4(),
        event_type=USER_ROLE_CHANGED,
        event_version=1,
        correlation_id=uuid4(),
        producer="auth-service",
        payload=UserRoleChangedV1(
            user_id=user_id, old_role=old_role, new_role=new_role, changed_by=uuid4(), changed_at=at
        ),
    )


def outgoing(envelope: Envelope[Any], topic: str = AUTH_TOPIC) -> OutgoingMessage:
    key = str(getattr(envelope.payload, "user_id", ""))
    return OutgoingMessage(topic, key, envelope.model_dump_json().encode())


def incoming(envelope: Envelope[Any], offset: int = 0, topic: str = AUTH_TOPIC) -> IncomingMessage:
    message = outgoing(envelope, topic)
    return IncomingMessage(topic, 0, offset, message.key, message.value)
