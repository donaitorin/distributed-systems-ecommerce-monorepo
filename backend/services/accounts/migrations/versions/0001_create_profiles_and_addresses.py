import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "profiles",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=True),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("role_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("name", sa.String(length=100), nullable=True),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "email IS NULL OR email = lower(email)", name=op.f("ck_profiles_email_lowercase")
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_profiles")),
    )
    op.create_index(
        "ix_profiles_email", "profiles", ["email"], postgresql_ops={"email": "text_pattern_ops"}
    )
    op.create_index(
        "ix_profiles_created_at_user_id",
        "profiles",
        [sa.text("created_at DESC"), sa.text("user_id DESC")],
    )
    op.create_index(
        "ix_profiles_role_created_at_user_id",
        "profiles",
        ["role", sa.text("created_at DESC"), sa.text("user_id DESC")],
    )
    op.create_table(
        "addresses",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recipient_name", sa.String(length=100), nullable=False),
        sa.Column("line1", sa.String(length=200), nullable=False),
        sa.Column("line2", sa.String(length=200), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=False),
        sa.Column("region", sa.String(length=100), nullable=True),
        sa.Column("postal_code", sa.String(length=20), nullable=False),
        sa.Column("country", sa.String(length=2), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("country ~ '^[A-Z]{2}$'", name=op.f("ck_addresses_country_alpha2")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["profiles.user_id"],
            name=op.f("fk_addresses_user_id_profiles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_addresses")),
    )
    op.create_index(op.f("ix_addresses_user_id"), "addresses", ["user_id"])


def downgrade() -> None:
    op.drop_table("addresses")
    op.drop_table("profiles")
