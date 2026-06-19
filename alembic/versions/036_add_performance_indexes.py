"""add performance indexes"""

revision = "036"
down_revision = "035"
branch_labels = None
depends_on = None

from alembic import op


def upgrade():
    # attendance — most queried table
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_att_date_section
        ON attendance (attendance_date, section_id);
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_att_student_year_status
        ON attendance (student_id, academic_year_id, status);
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_att_window_date
        ON attendance (attendance_window_id, attendance_date);
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_att_section_date_status
        ON attendance (section_id, attendance_date, status);
    """)

    # student_enrollments — joined on almost every query
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_enroll_section_year_status
        ON student_enrollments (section_id, academic_year_id, status);
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_enroll_student_year
        ON student_enrollments (student_id, academic_year_id);
    """)

    # student_faces — partial index, active only
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_face_student_active
        ON student_faces (student_id)
        WHERE is_active = TRUE;
    """)

    # attendance_windows — partial index, active only
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_window_section_active
        ON attendance_windows (section_id)
        WHERE is_active = TRUE;
    """)

    # timetable_entries
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_tt_entry_slot_year
        ON timetable_entries (period_slot_id, academic_year_id);
    """)

    # cameras — partial index, active only
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_camera_section_active
        ON cameras (section_id)
        WHERE is_active = TRUE;
    """)

    # detections — for review queue
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_detection_status_time
        ON detections (match_status, detected_at)
        WHERE match_status = 'LOW_CONFIDENCE';
    """)


def downgrade():
    for idx in [
        "idx_att_date_section", "idx_att_student_year_status",
        "idx_att_window_date", "idx_att_section_date_status",
        "idx_enroll_section_year_status", "idx_enroll_student_year",
        "idx_face_student_active", "idx_window_section_active",
        "idx_tt_entry_slot_year", "idx_camera_section_active",
        "idx_detection_status_time",
    ]:
        op.execute(f"DROP INDEX IF EXISTS {idx};")
