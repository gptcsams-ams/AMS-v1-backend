"""create auth_tokens table — replaces Redis for auth token storage"""

revision = "035"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


def upgrade():
    op.create_table(
        "auth_tokens",
        sa.Column("id",         UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id",    UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token",      sa.Text(), nullable=False, unique=True),
        sa.Column("token_type", sa.String(20), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("now()")),
    )
    op.create_index("idx_auth_tokens_token",   "auth_tokens", ["token"])
    op.create_index("idx_auth_tokens_expires", "auth_tokens", ["expires_at"])
    op.create_index("idx_auth_tokens_user",    "auth_tokens", ["user_id"])


def downgrade():
    op.drop_table("auth_tokens")
