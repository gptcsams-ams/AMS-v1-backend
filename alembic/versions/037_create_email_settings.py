"""create email_settings table

Revision ID: 037
Revises: g7h8i9j0k1l2
Create Date: 2026-06-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "037"
down_revision = "g7h8i9j0k1l2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "email_settings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("branch_id", UUID(as_uuid=True),
                  sa.ForeignKey("branches.id", ondelete="CASCADE"),
                  nullable=False),

        # Sender identity (what parents see)
        sa.Column("sender_name",  sa.String(255), nullable=True),
        sa.Column("sender_email", sa.String(255), nullable=True),

        # SMTP connection
        sa.Column("smtp_host",     sa.String(255), server_default="smtp.gmail.com"),
        sa.Column("smtp_port",     sa.Integer(),   server_default="587"),
        sa.Column("smtp_user",     sa.String(255), nullable=True),
        sa.Column("smtp_password", sa.Text(),      nullable=True),
        # ↑ Stored encrypted via Fernet — never plain text

        # Behaviour flags
        sa.Column("use_tls",   sa.Boolean(), server_default=sa.text("true")),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("false")),
        # is_active = False until admin saves valid credentials

        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("now()")),
    )

    # One config per branch
    op.create_index(
        "idx_email_settings_branch",
        "email_settings", ["branch_id"], unique=True,
    )


def downgrade() -> None:
    op.drop_index("idx_email_settings_branch", table_name="email_settings")
    op.drop_table("email_settings")
