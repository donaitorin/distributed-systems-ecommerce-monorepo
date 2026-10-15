from sqlalchemy import Column, DateTime, MetaData, String, Table, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID


def processed_events_table(metadata: MetaData, name: str = "processed_events") -> Table:
    return Table(
        name,
        metadata,
        Column("consumer_group", String(200), primary_key=True),
        Column("event_id", PG_UUID(as_uuid=True), primary_key=True),
        Column("processed_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
