from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

EVENT_TYPE_PATTERN = r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$"


class Envelope[PayloadT: BaseModel](BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    event_id: UUID = Field(default_factory=uuid4)
    event_type: str = Field(pattern=EVENT_TYPE_PATTERN)
    event_version: int = Field(ge=1)
    occurred_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))
    correlation_id: UUID
    producer: str = Field(min_length=1)
    payload: PayloadT

    @field_validator("occurred_at")
    @classmethod
    def normalize_to_utc(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)
