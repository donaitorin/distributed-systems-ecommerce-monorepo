from datetime import UTC, datetime, timedelta
from typing import Any

START = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)

ADDRESS: dict[str, Any] = {
    "recipient_name": "Ada Lovelace",
    "line1": "12 Analytical St",
    "line2": "Floor 2",
    "city": "London",
    "region": "Greater London",
    "postal_code": "N1 9GU",
    "country": "GB",
    "phone": "+442071234567",
}


class SteppingClock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float = 0, days: float = 0) -> None:
        self.now += timedelta(seconds=seconds, days=days)
