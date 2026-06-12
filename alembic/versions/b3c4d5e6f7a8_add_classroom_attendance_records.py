"""add classroom_attendance_records table

Revision ID: b3c4d5e6f7a8
Revises: a1b2c3d4e5f6
Create Date: 2026-06-11

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "b3c4d5e6f7a8"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "classroom_attendance_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "timetable_entry_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("timetable_entries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "student_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("students.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column(
            "marked_by_teacher_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("teacher_profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()")),
    )

    op.create_unique_constraint(
        "uq_classroom_attendance",
        "classroom_attendance_records",
        ["timetable_entry_id", "student_id", "date"],
    )
    op.create_index("idx_car_entry_date", "classroom_attendance_records",
                    ["timetable_entry_id", "date"])
    op.create_index("idx_car_student", "classroom_attendance_records", ["student_id"])
    op.create_index("idx_car_teacher", "classroom_attendance_records",
                    ["marked_by_teacher_id"])


def downgrade() -> None:
    op.drop_table("classroom_attendance_records")
