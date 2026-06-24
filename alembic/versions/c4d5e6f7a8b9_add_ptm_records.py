"""add ptm_records table

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-06-17

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "c4d5e6f7a8b9"
down_revision = "b3c4d5e6f7a8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ptm_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "student_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("students.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "parent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("parents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "teacher_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("teacher_profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("meeting_date", sa.Date(), nullable=False),
        sa.Column("discussion", sa.Text(), nullable=False),
        sa.Column("action_taken", sa.Text(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="OPEN"),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()")),
    )
    op.create_index("idx_ptm_student_date", "ptm_records", ["student_id", "meeting_date"])
    op.create_index("idx_ptm_parent_id", "ptm_records", ["parent_id"])
    op.create_index("idx_ptm_teacher_id", "ptm_records", ["teacher_id"])


def downgrade() -> None:
    op.drop_table("ptm_records")
