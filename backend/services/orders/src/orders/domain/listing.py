from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from orders.domain.status import OrderStatus


@dataclass(frozen=True, slots=True)
class OrderFilters:
    status: OrderStatus | None = None
    created_from: datetime | None = None
    created_to: datetime | None = None


@dataclass(frozen=True, slots=True)
class Position:
    created_at: datetime
    order_id: UUID
