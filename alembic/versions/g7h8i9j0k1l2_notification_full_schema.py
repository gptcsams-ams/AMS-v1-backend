"""Notification full schema — NotificationRule + upgrade Notification + NotificationTemplate

Revision ID: g7h8i9j0k1l2
Revises: f1a2b3c4d5e6
Create Date: 2026-06-23
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "g7h8i9j0k1l2"
down_revision = "036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── notification_templates: add updated_at ──────────────────────────────
    op.add_column(
        "notification_templates",
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
    )

    # ── notification_rules (new table) ─────────────────────────────────────
    op.create_table(
        "notification_rules",
        sa.Column("id",               UUID(as_uuid=True), primary_key=True),
        sa.Column("branch_id",        UUID(as_uuid=True),
                  sa.ForeignKey("branches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("trigger_type",     sa.String(50),  nullable=False),
        sa.Column("channel",          sa.String(20),  nullable=False),
        sa.Column("is_enabled",       sa.Boolean,     nullable=False, server_default="true"),
        sa.Column("throttle_minutes", sa.Integer,     nullable=True),
        sa.Column("send_time_from",   sa.Time,        nullable=True),
        sa.Column("send_time_to",     sa.Time,        nullable=True),
        sa.Column("created_at",       sa.TIMESTAMP(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at",       sa.TIMESTAMP(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("branch_id", "trigger_type", "channel", name="uq_notif_rule"),
    )
    op.create_index("idx_notif_rule_branch", "notification_rules", ["branch_id"])

    # ── notifications: upgrade schema ──────────────────────────────────────
    # Drop old columns that no longer exist in the model
    op.drop_column("notifications", "recipient_id")
    op.drop_column("notifications", "recipient_phone")
    op.drop_column("notifications", "recipient_email")
    op.drop_column("notifications", "reference_id")
    op.drop_column("notifications", "reference_type")
    op.drop_column("notifications", "message")

    # Add new columns
    op.add_column(
        "notifications",
        sa.Column("branch_id", UUID(as_uuid=True),
                  sa.ForeignKey("branches.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column(
        "notifications",
        sa.Column("student_id", UUID(as_uuid=True),
                  sa.ForeignKey("students.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column(
        "notifications",
        sa.Column("parent_id", UUID(as_uuid=True),
                  sa.ForeignKey("parents.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column(
        "notifications",
        sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
    )
    op.add_column(
        "notifications",
        sa.Column("provider_message_id", sa.String(255), nullable=True),
    )
    op.add_column(
        "notifications",
        sa.Column("payload", JSONB, nullable=False, server_default="{}"),
    )
    op.add_column(
        "notifications",
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("now()"), nullable=True),
    )

    # Indexes
    op.create_index("idx_notif_branch",   "notifications", ["branch_id"])
    op.create_index("idx_notif_student",  "notifications", ["student_id"])
    op.create_index("idx_notif_provider", "notifications", ["provider_message_id"])


def downgrade() -> None:
    # Reverse notifications changes
    op.drop_index("idx_notif_provider", "notifications")
    op.drop_index("idx_notif_student",  "notifications")
    op.drop_index("idx_notif_branch",   "notifications")

    op.drop_column("notifications", "updated_at")
    op.drop_column("notifications", "payload")
    op.drop_column("notifications", "provider_message_id")
    op.drop_column("notifications", "retry_count")
    op.drop_column("notifications", "parent_id")
    op.drop_column("notifications", "student_id")
    op.drop_column("notifications", "branch_id")

    op.add_column("notifications", sa.Column("message",         sa.Text))
    op.add_column("notifications", sa.Column("reference_type",  sa.String(50)))
    op.add_column("notifications", sa.Column("reference_id",    UUID(as_uuid=True)))
    op.add_column("notifications", sa.Column("recipient_email", sa.String(255)))
    op.add_column("notifications", sa.Column("recipient_phone", sa.String(20)))
    op.add_column("notifications", sa.Column("recipient_id",    UUID(as_uuid=True)))

    # Drop notification_rules
    op.drop_index("idx_notif_rule_branch", "notification_rules")
    op.drop_table("notification_rules")

    # Drop updated_at from templates
    op.drop_column("notification_templates", "updated_at")
