from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class ParentCreate(BaseModel):
    user_id: UUID
    full_name: str
    contact_number: str
    email: Optional[EmailStr] = None


class ParentRegister(BaseModel):
    """Create a parent together with their login User and student links.

    - username  → display name shown in the Parent Portal
    - email + password → the only credentials the parent logs in with
    - admission_numbers → one or more students to link to this parent
    """
    username: str
    email: EmailStr
    password: str = Field(min_length=6)
    contact_number: str
    admission_numbers: list[str] = Field(min_length=1)
    relationship_type: str = "GUARDIAN"
    occupation: Optional[str] = None
    address: Optional[str] = None

    @field_validator("admission_numbers")
    @classmethod
    def _clean_admissions(cls, v: list[str]) -> list[str]:
        cleaned = [a.strip() for a in v if a and a.strip()]
        # de-duplicate while preserving order
        seen: set[str] = set()
        out: list[str] = []
        for a in cleaned:
            if a not in seen:
                seen.add(a)
                out.append(a)
        if not out:
            raise ValueError("Select at least one student admission number.")
        return out


class ParentEntry(BaseModel):
    """One parent (Father or Mother) in a family-registration request.

    No password field — the server generates it as the parent's first name +
    the last 4 digits of their contact number (plain, no spaces or symbols).
    """
    name: str
    email: EmailStr
    contact_number: str
    occupation: Optional[str] = None


class ParentFamilyRegister(BaseModel):
    """Create a Father and/or a Mother account in one request, each linked to
    the same student(s). At least one of father/mother must be provided.
    """
    father: Optional[ParentEntry] = None
    mother: Optional[ParentEntry] = None
    address: Optional[str] = None
    admission_numbers: list[str] = Field(min_length=1)

    @field_validator("admission_numbers")
    @classmethod
    def _clean_admissions(cls, v: list[str]) -> list[str]:
        cleaned = [a.strip() for a in v if a and a.strip()]
        seen: set[str] = set()
        out: list[str] = []
        for a in cleaned:
            if a not in seen:
                seen.add(a)
                out.append(a)
        if not out:
            raise ValueError("Select at least one student admission number.")
        return out


class CreatedParentInfo(BaseModel):
    """Returned after creating a parent — includes the generated password so the
    admin can hand the credentials to the parent (shown once, not stored plain).
    """
    id: UUID
    full_name: str
    email: str
    relationship_type: str
    password: str


class ParentFamilyResponse(BaseModel):
    parents: list[CreatedParentInfo]


class ParentUpdate(BaseModel):
    full_name: Optional[str] = None
    contact_number: Optional[str] = None
    email: Optional[EmailStr] = None
    address: Optional[str] = None
    occupation: Optional[str] = None


class ParentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    full_name: str
    contact_number: str
    email: Optional[str] = None
    address: Optional[str] = None
    occupation: Optional[str] = None
    created_at: datetime
    children_count: Optional[int] = None


class ParentStudentLinkCreate(BaseModel):
    student_id: UUID
    relationship_type: str
    is_primary: bool = False


# ── Parent Portal — children with context ──────────────────────────────────────

class ChildEnrollment(BaseModel):
    section_id: Optional[UUID] = None
    section_name: Optional[str] = None
    year_id: Optional[UUID] = None
    roll_number: Optional[str] = None
    status: Optional[str] = None


class ChildSummary(BaseModel):
    student_id: UUID
    first_name: str
    last_name: str
    admission_number: Optional[str] = None
    student_photo_url: Optional[str] = None
    relationship_type: Optional[str] = None
    is_primary: bool = False
    enrollment: Optional[ChildEnrollment] = None
    today_status: Optional[str] = None       # PRESENT | ABSENT | LATE | EXCUSED | None
    attendance_pct: float = 0.0
    pending_leaves: int = 0


class ChildrenResponse(BaseModel):
    data: list[ChildSummary]
