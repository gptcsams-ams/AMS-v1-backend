"""
Single CTE query replaces 6-8 separate DB calls on dashboard load.
"""
from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


async def get_dashboard_stats(
    branch_id:  str,
    year_id:    str,
    today_date: str,
    db: AsyncSession,
) -> dict:
    # asyncpg requires a real date object, not a string
    if isinstance(today_date, str):
        today_date = date.fromisoformat(today_date)
    result = await db.execute(text("""
        WITH enrolled AS (
            SELECT COUNT(DISTINCT se.student_id) AS total
            FROM student_enrollments se
            JOIN sections s ON s.id = se.section_id
            JOIN classes  c ON c.id = s.class_id
            WHERE c.branch_id        = :branch_id
              AND se.academic_year_id = :year_id
              AND se.status           = 'ACTIVE'
        ),
        today_att AS (
            SELECT a.status, COUNT(*) AS cnt
            FROM attendance a
            JOIN sections s ON s.id = a.section_id
            JOIN classes  c ON c.id = s.class_id
            WHERE c.branch_id        = :branch_id
              AND a.academic_year_id  = :year_id
              AND a.attendance_date   = :today
            GROUP BY a.status
        ),
        cam_stats AS (
            SELECT
                COUNT(*)                                              AS total_cameras,
                COUNT(*) FILTER (WHERE cam.stream_status = 'ACTIVE') AS online_cameras
            FROM cameras cam
            JOIN sections s ON s.id = cam.section_id
            JOIN classes  c ON c.id = s.class_id
            WHERE c.branch_id = :branch_id
              AND cam.is_active = TRUE
        ),
        win_stats AS (
            SELECT COUNT(*) AS active_windows
            FROM attendance_windows aw
            JOIN sections s ON s.id = aw.section_id
            JOIN classes  c ON c.id = s.class_id
            WHERE c.branch_id = :branch_id AND aw.is_active = TRUE
        ),
        defaulters AS (
            SELECT COUNT(DISTINCT sub.student_id) AS cnt
            FROM (
                SELECT
                    a.student_id,
                    COUNT(*) FILTER (
                        WHERE a.status IN ('PRESENT','LATE')
                    )::float / NULLIF(COUNT(*), 0) AS att_pct
                FROM attendance a
                JOIN sections s ON s.id = a.section_id
                JOIN classes  c ON c.id = s.class_id
                WHERE c.branch_id = :branch_id AND a.academic_year_id = :year_id
                GROUP BY a.student_id
                HAVING COUNT(*) > 0
            ) sub
            WHERE sub.att_pct < 0.75
        )
        SELECT
            e.total                                                     AS total_students,
            COALESCE(SUM(CASE WHEN ta.status='PRESENT' THEN ta.cnt END), 0) AS present_today,
            COALESCE(SUM(CASE WHEN ta.status='ABSENT'  THEN ta.cnt END), 0) AS absent_today,
            COALESCE(SUM(CASE WHEN ta.status='LATE'    THEN ta.cnt END), 0) AS late_today,
            cs.total_cameras,
            cs.online_cameras,
            ws.active_windows,
            d.cnt AS defaulters_count
        FROM enrolled e
        CROSS JOIN cam_stats cs
        CROSS JOIN win_stats ws
        CROSS JOIN defaulters d
        LEFT JOIN today_att ta ON TRUE
        GROUP BY e.total, cs.total_cameras, cs.online_cameras,
                 ws.active_windows, d.cnt
    """), {"branch_id": branch_id, "year_id": year_id, "today": today_date})

    row = result.mappings().fetchone()
    if not row:
        return {k: 0 for k in [
            "total_students", "present_today", "present_pct",
            "absent_today", "absent_pct", "late_today", "late_pct",
            "total_cameras", "active_cameras", "active_windows",
            "defaulters_count", "alerts_today",
        ]}

    total   = int(row["total_students"] or 0)
    present = int(row["present_today"]  or 0)
    absent  = int(row["absent_today"]   or 0)
    late    = int(row["late_today"]     or 0)

    return {
        "total_students":   total,
        "present_today":    present,
        "present_pct":      round(present / total * 100, 2) if total else 0,
        "absent_today":     absent,
        "absent_pct":       round(absent  / total * 100, 2) if total else 0,
        "late_today":       late,
        "late_pct":         round(late    / total * 100, 2) if total else 0,
        "total_cameras":    int(row["total_cameras"]    or 0),
        "active_cameras":   int(row["online_cameras"]   or 0),
        "active_windows":   int(row["active_windows"]   or 0),
        "defaulters_count": int(row["defaulters_count"] or 0),
        "alerts_today":     0,
    }
