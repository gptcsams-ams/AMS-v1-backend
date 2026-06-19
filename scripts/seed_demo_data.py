"""
Full demo seed — wires everything to the dashboard.

What it creates:
  • School + Branch (or reuses existing)
  • Academic Year 2025-2026 (marked current)
  • 4 Grades (9-12) × 2 Sections (A/B) = 8 sections
  • 10 Subjects
  • 8 Teachers  (password: Teacher@123)
  • 20 Students enrolled across sections
  • Attendance Windows  (1 per section, "Morning Roll-call")
  • 30 days of attendance records  → dashboard stat cards populate instantly

Run from  backend/:
    python -m scripts.seed_demo_data
"""

import asyncio
import random
from datetime import date, timedelta, time

from sqlalchemy import select, text

from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.academic_class import AcademicClass
from app.models.academic_year import AcademicYear
from app.models.attendance import Attendance
from app.models.attendance_window import AttendanceWindow
from app.models.branch import Branch
from app.models.school import School
from app.models.section import Section
from app.models.student import Student
from app.models.student_enrollment import StudentEnrollment
from app.models.subject import Subject
from app.models.teacher_profile import TeacherProfile
from app.models.user import User


# ── School / Branch ───────────────────────────────────────────────────────────
SCHOOL_NAME   = "GPTCS"          # matches existing DB record
BRANCH_NAME   = "Main Campus"
ADMIN_EMAIL   = "admin@gptcs.com"

SCHOOL_DATA   = dict(
    name    = SCHOOL_NAME,
    address = "45 Knowledge Park, Sector 12",
    city    = "Hyderabad",
    state   = "Telangana",
    area    = "Madhapur",
    pincode = "500081",
    phone   = "040-40404040",
    email   = "info@gptcs.com",
    board   = "CBSE",
)

# ── Academic year ──────────────────────────────────────────────────────────────
YEAR_NAME  = "2025-2026"         # will be created and set as current
YEAR_START = date(2025, 6, 1)
YEAR_END   = date(2026, 3, 31)

# ── Grades & Sections ─────────────────────────────────────────────────────────
GRADES = ["9", "10", "11", "12"]          # each gets sections A & B

# ── Subjects ──────────────────────────────────────────────────────────────────
SUBJECTS = [
    dict(name="Mathematics",        code="MATH",  color="#6366F1"),
    dict(name="Physics",            code="PHY",   color="#0EA5E9"),
    dict(name="Chemistry",          code="CHEM",  color="#10B981"),
    dict(name="Biology",            code="BIO",   color="#84CC16"),
    dict(name="English",            code="ENG",   color="#F59E0B"),
    dict(name="Computer Science",   code="CS",    color="#8B5CF6"),
    dict(name="Social Studies",     code="SOC",   color="#EC4899"),
    dict(name="Hindi",              code="HINDI", color="#EF4444"),
    dict(name="Physical Education", code="PE",    color="#14B8A6"),
    dict(name="Economics",          code="ECO",   color="#F97316"),
]

# ── Teachers ──────────────────────────────────────────────────────────────────
TEACHERS = [
    dict(name="Dr. Ananya Sharma",      email="ananya.sharma@gptcs.com",    emp="EMP001", dept="Mathematics",        desig="Senior Teacher"),
    dict(name="Mr. Rajesh Verma",       email="rajesh.verma@gptcs.com",     emp="EMP002", dept="Physics",            desig="Teacher"),
    dict(name="Ms. Priya Nair",         email="priya.nair@gptcs.com",       emp="EMP003", dept="Chemistry",          desig="Teacher"),
    dict(name="Mrs. Sunita Gupta",      email="sunita.gupta@gptcs.com",     emp="EMP004", dept="Biology",            desig="Senior Teacher"),
    dict(name="Mr. Arun Krishnamurthy", email="arun.k@gptcs.com",           emp="EMP005", dept="English",            desig="Teacher"),
    dict(name="Ms. Meera Iyer",         email="meera.iyer@gptcs.com",       emp="EMP006", dept="Computer Science",   desig="HOD"),
    dict(name="Mr. Vikram Patel",       email="vikram.patel@gptcs.com",     emp="EMP007", dept="Social Studies",     desig="Teacher"),
    dict(name="Mrs. Deepa Menon",       email="deepa.menon@gptcs.com",      emp="EMP008", dept="Hindi",              desig="Teacher"),
]

# ── Students — 20 total, spread 2-3 per section ───────────────────────────────
STUDENTS = [
    # Grade 9-A
    dict(fn="Aarav",     ln="Singh",     adm="GPTCS001", roll="01", grade="9",  sec="A", gen="Male",   dob=date(2010,3,15),  blood="O+",  ph="9800000001"),
    dict(fn="Diya",      ln="Sharma",    adm="GPTCS002", roll="02", grade="9",  sec="A", gen="Female", dob=date(2010,7,22),  blood="A+",  ph="9800000002"),
    dict(fn="Karan",     ln="Mehta",     adm="GPTCS003", roll="03", grade="9",  sec="A", gen="Male",   dob=date(2010,11,5),  blood="B+",  ph="9800000003"),
    # Grade 9-B
    dict(fn="Sneha",     ln="Patel",     adm="GPTCS004", roll="01", grade="9",  sec="B", gen="Female", dob=date(2010,1,30),  blood="AB+", ph="9800000004"),
    dict(fn="Rohan",     ln="Kumar",     adm="GPTCS005", roll="02", grade="9",  sec="B", gen="Male",   dob=date(2010,5,18),  blood="O-",  ph="9800000005"),
    dict(fn="Ananya",    ln="Nair",      adm="GPTCS006", roll="03", grade="9",  sec="B", gen="Female", dob=date(2010,9,12),  blood="A-",  ph="9800000006"),
    # Grade 10-A
    dict(fn="Arjun",     ln="Reddy",     adm="GPTCS007", roll="01", grade="10", sec="A", gen="Male",   dob=date(2009,2,28),  blood="B-",  ph="9800000007"),
    dict(fn="Priya",     ln="Iyer",      adm="GPTCS008", roll="02", grade="10", sec="A", gen="Female", dob=date(2009,4,10),  blood="O+",  ph="9800000008"),
    dict(fn="Siddharth", ln="Verma",     adm="GPTCS009", roll="03", grade="10", sec="A", gen="Male",   dob=date(2009,8,25),  blood="A+",  ph="9800000009"),
    # Grade 10-B
    dict(fn="Kavya",     ln="Joshi",     adm="GPTCS010", roll="01", grade="10", sec="B", gen="Female", dob=date(2009,12,14), blood="B+",  ph="9800000010"),
    dict(fn="Rahul",     ln="Gupta",     adm="GPTCS011", roll="02", grade="10", sec="B", gen="Male",   dob=date(2009,6,3),   blood="AB-", ph="9800000011"),
    dict(fn="Ishaan",    ln="Bose",      adm="GPTCS012", roll="03", grade="10", sec="B", gen="Male",   dob=date(2009,3,20),  blood="O+",  ph="9800000012"),
    # Grade 11-A
    dict(fn="Neha",      ln="Kulkarni",  adm="GPTCS013", roll="01", grade="11", sec="A", gen="Female", dob=date(2008,10,7),  blood="A+",  ph="9800000013"),
    dict(fn="Aditya",    ln="Pillai",    adm="GPTCS014", roll="02", grade="11", sec="A", gen="Male",   dob=date(2008,7,16),  blood="B+",  ph="9800000014"),
    dict(fn="Pooja",     ln="Agarwal",   adm="GPTCS015", roll="03", grade="11", sec="A", gen="Female", dob=date(2008,2,14),  blood="O-",  ph="9800000015"),
    # Grade 11-B
    dict(fn="Nikhil",    ln="Tiwari",    adm="GPTCS016", roll="01", grade="11", sec="B", gen="Male",   dob=date(2008,9,29),  blood="A+",  ph="9800000016"),
    dict(fn="Shreya",    ln="Banerjee",  adm="GPTCS017", roll="02", grade="11", sec="B", gen="Female", dob=date(2008,5,8),   blood="B+",  ph="9800000017"),
    # Grade 12-A
    dict(fn="Vikrant",   ln="Mishra",    adm="GPTCS018", roll="01", grade="12", sec="A", gen="Male",   dob=date(2007,11,21), blood="AB+", ph="9800000018"),
    dict(fn="Tanvi",     ln="Chopra",    adm="GPTCS019", roll="02", grade="12", sec="A", gen="Female", dob=date(2007,4,3),   blood="O+",  ph="9800000019"),
    # Grade 12-B
    dict(fn="Manav",     ln="Saxena",    adm="GPTCS020", roll="01", grade="12", sec="B", gen="Male",   dob=date(2007,8,17),  blood="A-",  ph="9800000020"),
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def random_status() -> str:
    """Weighted attendance: 80% PRESENT, 10% ABSENT, 10% LATE."""
    return random.choices(
        ["PRESENT", "ABSENT", "LATE"],
        weights=[80, 10, 10]
    )[0]


def school_days(start: date, end: date):
    """Yield weekdays (Mon–Sat) between start and end inclusive."""
    d = start
    while d <= end:
        if d.weekday() < 6:   # 0=Mon … 5=Sat
            yield d
        d += timedelta(days=1)


# ── Main ──────────────────────────────────────────────────────────────────────

async def seed() -> None:
    random.seed(42)

    async with AsyncSessionLocal() as db:

        # ── 1. Admin user ─────────────────────────────────────────────────────
        admin = (await db.execute(
            select(User).where(User.email == ADMIN_EMAIL)
        )).scalar_one_or_none()

        if not admin:
            print(f"  [!] Admin '{ADMIN_EMAIL}' not found — creating...")
            admin = User(
                name="GPTCS Admin",
                email=ADMIN_EMAIL,
                password=hash_password("ChangeMe123!"),
                role="SUPER_ADMIN",
                is_active=True,
                totp_enabled=False,
            )
            db.add(admin)
            await db.flush()
        else:
            print(f"  [=] Admin found: {ADMIN_EMAIL}")

        # ── 2. School ─────────────────────────────────────────────────────────
        school = (await db.execute(
            select(School).where(School.name == SCHOOL_NAME)
        )).scalar_one_or_none()

        if not school:
            school = School(**SCHOOL_DATA)
            db.add(school)
            await db.flush()
            print(f"  [+] School: {school.name}")
        else:
            print(f"  [=] School: {school.name}")

        # ── 3. Branch ─────────────────────────────────────────────────────────
        branch = (await db.execute(
            select(Branch).where(Branch.school_id == school.id, Branch.name == BRANCH_NAME)
        )).scalar_one_or_none()

        if not branch:
            branch = Branch(school_id=school.id, name=BRANCH_NAME, location="Madhapur, Hyderabad")
            db.add(branch)
            await db.flush()
            print(f"  [+] Branch: {branch.name}")
        else:
            print(f"  [=] Branch: {branch.name}")

        # Link admin to this branch if not already
        if admin.branch_id != branch.id:
            admin.branch_id = branch.id
            await db.flush()
            print(f"  [~] Admin linked to branch")

        # ── 4. Academic Year ──────────────────────────────────────────────────
        # Clear any other current year for this school first
        await db.execute(text(
            "UPDATE academic_years SET is_current=FALSE WHERE school_id=:sid AND name!=:name",
        ), {"sid": str(school.id), "name": YEAR_NAME})

        acad_year = (await db.execute(
            select(AcademicYear).where(
                AcademicYear.school_id == school.id,
                AcademicYear.name == YEAR_NAME
            )
        )).scalar_one_or_none()

        if not acad_year:
            acad_year = AcademicYear(
                school_id  = school.id,
                name       = YEAR_NAME,
                start_date = YEAR_START,
                end_date   = YEAR_END,
                is_current = True,
            )
            db.add(acad_year)
            await db.flush()
            print(f"  [+] Academic Year: {acad_year.name}")
        else:
            acad_year.is_current = True
            await db.flush()
            print(f"  [=] Academic Year: {acad_year.name}")

        # ── 5. Subjects ───────────────────────────────────────────────────────
        for sub_data in SUBJECTS:
            existing = (await db.execute(
                select(Subject).where(
                    Subject.branch_id == branch.id,
                    Subject.name == sub_data["name"]
                )
            )).scalar_one_or_none()
            if not existing:
                db.add(Subject(branch_id=branch.id, **sub_data))
                print(f"  [+] Subject: {sub_data['name']}")
        await db.flush()

        # ── 6. Classes & Sections ─────────────────────────────────────────────
        # section_map[grade][sec_letter] = Section ORM object
        section_map: dict[str, dict[str, Section]] = {}

        for grade in GRADES:
            cls = (await db.execute(
                select(AcademicClass).where(
                    AcademicClass.branch_id == branch.id,
                    AcademicClass.grade == grade
                )
            )).scalar_one_or_none()

            if not cls:
                cls = AcademicClass(branch_id=branch.id, grade=grade)
                db.add(cls)
                await db.flush()
                print(f"  [+] Class {grade}")

            section_map[grade] = {}
            for letter in ["A", "B"]:
                sec = (await db.execute(
                    select(Section).where(
                        Section.class_id == cls.id,
                        Section.name == letter
                    )
                )).scalar_one_or_none()

                if not sec:
                    sec = Section(class_id=cls.id, name=letter)
                    db.add(sec)
                    await db.flush()
                    print(f"       [+] Section {grade}-{letter}")

                section_map[grade][letter] = sec

        # ── 7. Teachers ───────────────────────────────────────────────────────
        for t in TEACHERS:
            user = (await db.execute(
                select(User).where(User.email == t["email"])
            )).scalar_one_or_none()

            if not user:
                user = User(
                    name       = t["name"],
                    email      = t["email"],
                    password   = hash_password("Teacher@123"),
                    role       = "TEACHER",
                    branch_id  = branch.id,
                    is_active  = True,
                    totp_enabled = False,
                )
                db.add(user)
                await db.flush()

                db.add(TeacherProfile(
                    user_id     = user.id,
                    branch_id   = branch.id,
                    employee_id = t["emp"],
                    department  = t["dept"],
                    designation = t["desig"],
                    contact_number = "9000000000",
                ))
                await db.flush()
                print(f"  [+] Teacher: {t['name']}")
            else:
                print(f"  [=] Teacher exists: {t['email']}")

        # ── 8. Students + Enrollments ─────────────────────────────────────────
        student_section_pairs: list[tuple[Student, Section]] = []

        for s in STUDENTS:
            student = (await db.execute(
                select(Student).where(Student.admission_number == s["adm"])
            )).scalar_one_or_none()

            section = section_map[s["grade"]][s["sec"]]

            if not student:
                student = Student(
                    branch_id        = branch.id,
                    first_name       = s["fn"],
                    last_name        = s["ln"],
                    dob              = s["dob"],
                    gender           = s["gen"],
                    blood_group      = s["blood"],
                    roll_number      = s["roll"],
                    admission_number = s["adm"],
                    contact_number   = s["ph"],
                    email            = f"{s['fn'].lower()}.{s['ln'].lower()}@student.gptcs.com",
                    join_date        = YEAR_START,
                    is_active        = True,
                )
                db.add(student)
                await db.flush()

                db.add(StudentEnrollment(
                    student_id       = student.id,
                    section_id       = section.id,
                    academic_year_id = acad_year.id,
                    roll_number      = s["roll"],
                    status           = "ACTIVE",
                    enrolled_at      = YEAR_START,
                ))
                await db.flush()
                print(f"  [+] Student: {s['fn']} {s['ln']}  -> Grade {s['grade']}-{s['sec']}")
            else:
                print(f"  [=] Student exists: {s['adm']}")

            student_section_pairs.append((student, section))

        # ── 9. Attendance Windows (1 per section) ─────────────────────────────
        window_map: dict[str, AttendanceWindow] = {}   # section_id → window

        for grade, sec_dict in section_map.items():
            for letter, sec in sec_dict.items():
                win_name = "Morning Roll-call"
                win = (await db.execute(
                    select(AttendanceWindow).where(
                        AttendanceWindow.section_id == sec.id,
                        AttendanceWindow.name == win_name
                    )
                )).scalar_one_or_none()

                if not win:
                    win = AttendanceWindow(
                        section_id              = sec.id,
                        name                    = win_name,
                        start_time              = time(8, 30),
                        end_time                = time(9, 30),
                        days_of_week            = [0, 1, 2, 3, 4, 5],  # Mon-Sat
                        is_manual_trigger       = False,
                        is_active               = True,
                        min_detections_required = 2,
                        min_presence_minutes    = 5,
                        confidence_threshold    = 0.65,
                        detection_start_offset_minutes   = 3,
                        opening_capture_duration_minutes = 10,
                        closing_capture_duration_minutes = 5,
                        late_threshold_minutes           = 15,
                    )
                    db.add(win)
                    await db.flush()
                    print(f"  [+] Window for Grade {grade}-{letter}")

                window_map[str(sec.id)] = win

        # ── 10. Attendance Records (last 30 school days + today) ───────────────
        today     = date.today()
        hist_start = today - timedelta(days=45)   # gives ~30 school days after filtering weekends
        days       = list(school_days(hist_start, today))

        existing_keys: set[str] = set()
        # Pre-fetch existing records for these students to avoid duplicates
        if student_section_pairs:
            student_ids = [str(st.id) for st, _ in student_section_pairs]
            rows = (await db.execute(text(
                "SELECT student_id::text, attendance_window_id::text, attendance_date::text "
                "FROM attendance WHERE student_id = ANY(:ids)",
            ), {"ids": student_ids})).fetchall()
            for r in rows:
                existing_keys.add(f"{r[0]}|{r[1]}|{r[2]}")

        inserted = 0
        for att_date in days:
            for student, section in student_section_pairs:
                win = window_map.get(str(section.id))
                if not win:
                    continue

                key = f"{student.id}|{win.id}|{att_date}"
                if key in existing_keys:
                    continue

                # Today is special: use present-heavy weights
                if att_date == today:
                    status = random.choices(["PRESENT","ABSENT","LATE"], weights=[85,8,7])[0]
                else:
                    status = random_status()

                db.add(Attendance(
                    student_id           = student.id,
                    section_id           = section.id,
                    academic_year_id     = acad_year.id,
                    attendance_window_id = win.id,
                    attendance_date      = att_date,
                    status               = status,
                    detection_count      = random.randint(2, 8) if status != "ABSENT" else 0,
                    data_confidence      = "HIGH",
                    marked_by            = "SYSTEM",
                    is_overridden        = False,
                ))
                existing_keys.add(key)
                inserted += 1

            # Flush every day to keep memory reasonable
            if inserted % 200 == 0 and inserted:
                await db.flush()

        await db.flush()
        await db.commit()

        print(f"\n  [+] Attendance records inserted: {inserted}")
        print("\n" + "="*55)
        print("  DEMO SEED COMPLETE")
        print("="*55)
        print(f"  School      : {SCHOOL_NAME}")
        print(f"  Branch      : {BRANCH_NAME}")
        print(f"  Acad Year   : {YEAR_NAME} (current)")
        print(f"  Grades      : 9, 10, 11, 12  (Sections A & B each)")
        print(f"  Subjects    : {len(SUBJECTS)}")
        print(f"  Teachers    : {len(TEACHERS)}  password: Teacher@123")
        print(f"  Students    : {len(STUDENTS)}  enrolled + attendance seeded")
        print(f"  Days seeded : {len(days)}  ({hist_start} → {today})")
        print("="*55)
        print(f"\n  Admin login : {ADMIN_EMAIL}  /  ChangeMe123!")
        print()


if __name__ == "__main__":
    asyncio.run(seed())
