from uuid import UUID, uuid4

from ecommerce_observability import get_request_id


def current_correlation_id() -> UUID:
    current = get_request_id()
    try:
        return UUID(current) if current else uuid4()
    except ValueError:
        return uuid4()
