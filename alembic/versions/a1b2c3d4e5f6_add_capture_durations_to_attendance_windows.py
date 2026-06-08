"""add capture durations to attendance_windows

Revision ID: a1b2c3d4e5f6
Revises: e9c1236500a8
Create Date: 2026-06-06

"""
from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f6"
down_revision = "e9c1236500a8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "attendance_windows",
        sa.Column(
            "opening_capture_duration_minutes",
            sa.Integer(),
            nullable=False,
            server_default="10",
        ),
    )
    op.add_column(
        "attendance_windows",
        sa.Column(
            "closing_capture_duration_minutes",
            sa.Integer(),
            nullable=False,
            server_default="5",
        ),
    )


def downgrade() -> None:
    op.drop_column("attendance_windows", "closing_capture_duration_minutes")
    op.drop_column("attendance_windows", "opening_capture_duration_minutes")
