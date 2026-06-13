import csv
import io
from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.academic_class import AcademicClass
from app.models.section import Section
from app.models.student import Student
from app.models.student_enrollment import StudentEnrollment


def _class_name_variants(name: str) -> list[str]:
    value = name.strip()
    variants = [value]
    if value.lower().startswith("grade "):
        variants.append("Class " + value[6:].strip())
    if value.lower().startswith("class "):
        variants.append("Grade " + value[6:].strip())
    return list(dict.fromkeys(variants))


async def import_students_csv(
    db: AsyncSession,
    csv_text: str,
    academic_year_id: UUID | None,
    branch_id: UUID | None,
) -> dict:
    reader = csv.DictReader(io.StringIO(csv_text))
    success = 0
    errors: list[dict] = []

    for row_number, row in enumerate(reader, start=2):
        try:
            admission_number = (row.get("admission_number") or "").strip()
            roll_number = (row.get("roll_number") or admission_number).strip()
            class_name = (row.get("class") or row.get("grade") or "").strip()
            section_name = (row.get("section") or "").strip()

            if not branch_id:
                raise ValueError("No branch is selected")
            if not admission_number:
                raise ValueError("Admission number is required")
            if not row.get("first_name") or not row.get("last_name"):
                raise ValueError("First name and last name are required")

            student = (await db.execute(
                select(Student).where(Student.admission_number == admission_number)
            )).scalar_one_or_none()

            if not student:
                student = Student(
                    branch_id=branch_id,
                    first_name=row["first_name"].strip(),
                    last_name=row["last_name"].strip(),
                    admission_number=admission_number,
                    roll_number=roll_number,
                    dob=date.fromisoformat(row["dob"]) if row.get("dob") else None,
                    gender=(row.get("gender") or None),
                    contact_number=(row.get("contact_number") or None),
                    email=(row.get("email") or None),
                    address=(row.get("address") or None),
                    group_name=(row.get("group_name") or None),
                    join_date=date.fromisoformat(row["join_date"]) if row.get("join_date") else None,
                )
                db.add(student)
                await db.flush()

            if academic_year_id and class_name and section_name:
                academic_class = (await db.execute(
                    select(AcademicClass).where(
                        AcademicClass.branch_id == branch_id,
                        AcademicClass.grade.in_(_class_name_variants(class_name)),
                    )
                )).scalar_one_or_none()
                if not academic_class:
                    raise ValueError(f"Class '{class_name}' was not found")

                section = (await db.execute(
                    select(Section).where(
                        Section.class_id == academic_class.id,
                        Section.name == section_name,
                    )
                )).scalar_one_or_none()
                if not section:
                    raise ValueError(f"Section '{section_name}' was not found for {academic_class.grade}")

                enrollment = (await db.execute(
                    select(StudentEnrollment).where(
                        StudentEnrollment.student_id == student.id,
                        StudentEnrollment.academic_year_id == academic_year_id,
                    )
                )).scalar_one_or_none()
                if not enrollment:
                    db.add(StudentEnrollment(
                        student_id=student.id,
                        section_id=section.id,
                        academic_year_id=academic_year_id,
                        roll_number=roll_number,
                        enrolled_at=student.join_date or date.today(),
                    ))

            success += 1
        except Exception as exc:
            await db.rollback()
            errors.append({"row": row_number, "reason": str(exc)})

    await db.commit()
    return {"success": success, "errors": errors}
