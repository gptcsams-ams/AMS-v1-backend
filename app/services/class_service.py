"""
Replaces N queries (one per section) with one GROUP BY query.
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


async def get_class_sections_with_stats(
    class_id: str,
    year_id:  str | None,
    db:       AsyncSession,
) -> list:
    # When no year is available, return sections without enrollment/attendance stats
    if not year_id:
        result = await db.execute(text("""
            SELECT
                sec.id::text        AS id,
                sec.class_id::text  AS class_id,
                sec.name            AS name,
                c.grade,
                0                   AS student_count,
                0                   AS face_enrolled_count,
                0                   AS present_today,
                0                   AS total_today,
                NULL                AS month_avg_pct,
                0                   AS defaulter_count
            FROM sections sec
            JOIN classes c ON c.id = sec.class_id
            WHERE c.id = :class_id
            ORDER BY sec.name
        """), {"class_id": class_id})
        return [dict(r) for r in result.mappings().fetchall()]

    result = await db.execute(text("""
        SELECT
            sec.id::text                                             AS id,
            sec.class_id::text                                       AS class_id,
            sec.name                                                 AS name,
            c.grade,
            COUNT(DISTINCT se.student_id)                           AS student_count,
            COUNT(DISTINCT se.student_id)
                FILTER (WHERE COALESCE(fc.face_count,0) >= 3)       AS face_enrolled_count,
            COALESCE(today.present_today, 0)                        AS present_today,
            COALESCE(today.total_today,   0)                        AS total_today,
            ROUND(
                COALESCE(month_att.present_month, 0)::numeric
                / NULLIF(COALESCE(month_att.total_month, 0), 0)
                * 100, 1
            )                                                        AS month_avg_pct,
            COALESCE(def_sub.defaulter_count, 0)                    AS defaulter_count

        FROM sections sec
        JOIN classes c ON c.id = sec.class_id
        LEFT JOIN student_enrollments se
               ON se.section_id = sec.id
              AND se.academic_year_id = CAST(:year_id AS uuid)
              AND se.status = 'ACTIVE'

        LEFT JOIN LATERAL (
            SELECT COUNT(*) AS face_count
            FROM student_faces sf2
            WHERE sf2.student_id = se.student_id AND sf2.is_active = TRUE
        ) fc ON TRUE

        LEFT JOIN LATERAL (
            SELECT
                COUNT(*) FILTER (WHERE status IN ('PRESENT','LATE')) AS present_today,
                COUNT(*)                                               AS total_today
            FROM attendance a1
            WHERE a1.section_id = sec.id
              AND a1.academic_year_id = CAST(:year_id AS uuid)
              AND a1.attendance_date  = CURRENT_DATE
        ) today ON TRUE

        LEFT JOIN LATERAL (
            SELECT
                COUNT(*) FILTER (WHERE status IN ('PRESENT','LATE')) AS present_month,
                COUNT(*)                                               AS total_month
            FROM attendance a2
            WHERE a2.section_id = sec.id
              AND a2.academic_year_id = CAST(:year_id AS uuid)
              AND a2.attendance_date >= date_trunc('month', CURRENT_DATE)
        ) month_att ON TRUE

        LEFT JOIN LATERAL (
            SELECT COUNT(*) AS defaulter_count
            FROM student_enrollments se2
            WHERE se2.section_id = sec.id
              AND se2.academic_year_id = CAST(:year_id AS uuid)
              AND se2.status = 'ACTIVE'
              AND (
                SELECT COUNT(*) FROM attendance ax
                WHERE ax.student_id = se2.student_id
                  AND ax.academic_year_id = CAST(:year_id AS uuid)
              ) > 0
              AND (
                SELECT COUNT(*) FILTER (WHERE ax2.status IN ('PRESENT','LATE'))::float
                       / NULLIF(COUNT(*), 0)
                FROM attendance ax2
                WHERE ax2.student_id = se2.student_id
                  AND ax2.academic_year_id = CAST(:year_id AS uuid)
              ) < 0.75
        ) def_sub ON TRUE

        WHERE c.id = :class_id
        GROUP BY sec.id, sec.class_id, sec.name, c.grade,
                 today.present_today, today.total_today,
                 month_att.present_month, month_att.total_month,
                 def_sub.defaulter_count
        ORDER BY sec.name
    """), {"class_id": class_id, "year_id": year_id})

    return [dict(r) for r in result.mappings().fetchall()]
