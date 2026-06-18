revision = "initial"
down_revision = None
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa

def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    op.create_table(
        "virtual_keys",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("hashed_key", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("monthly_token_limit", sa.BigInteger(), nullable=True),
        sa.Column("rpm_limit", sa.Integer(), nullable=True),
        sa.Column("allowed_model_groups", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_virtual_keys_hashed_key"),
        "virtual_keys",
        ["hashed_key"],
        unique=True,
    )

    op.create_table(
        "credentials",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("encrypted_secret", sa.String(length=2048), nullable=False),
        sa.Column("base_url", sa.String(length=512), nullable=True),
        sa.Column("models", sa.JSON(), nullable=True),
        sa.Column("quota_total_tokens", sa.BigInteger(), nullable=True),
        sa.Column("quota_used_tokens", sa.BigInteger(), nullable=False),
        sa.Column("quota_window", sa.Integer(), nullable=True),
        sa.Column("reset_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rpm_limit", sa.Integer(), nullable=True),
        sa.Column("concurrency_limit", sa.Integer(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("weight", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "usage_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("virtual_key_id", sa.UUID(), nullable=True),
        sa.Column("credential_id", sa.UUID(), nullable=True),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("est_cost", sa.Float(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["credential_id"], ["credentials.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["virtual_key_id"], ["virtual_keys.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("payload_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("usage_events")
    op.drop_table("credentials")
    op.drop_table("virtual_keys")
    op.drop_table("users")
