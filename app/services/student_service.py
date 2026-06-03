import csv
import io
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.student import Student


async def import_students_csv(db: AsyncSession, csv_text: str) -> int:
    reader = csv.DictReader(io.StringIO(csv_text))
    count = 0
    for row in reader:
        student = Student(
            branch_id=row["branch_id"],
            first_name=row["first_name"],
            last_name=row["last_name"],
            admission_number=row["admission_number"],
            roll_number=row.get("roll_number") or row["admission_number"],
            dob=date.fromisoformat(row["dob"]) if row.get("dob") else None,
        )
        db.add(student)
        count += 1
    await db.commit()
    return count
