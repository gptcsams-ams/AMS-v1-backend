"""add ptm schedule fields

Revision ID: c5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-06-18

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "c5e6f7a8b9c0"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ptm_records",
        sa.Column(
            "section_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sections.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("ptm_records", sa.Column("meeting_time", sa.Time(), nullable=True))
    op.create_index("idx_ptm_section_date", "ptm_records", ["section_id", "meeting_date"])


def downgrade() -> None:
    op.drop_index("idx_ptm_section_date", table_name="ptm_records")
    op.drop_column("ptm_records", "meeting_time")
    op.drop_column("ptm_records", "section_id")
