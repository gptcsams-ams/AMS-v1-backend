from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel


class GradeMappingItem(BaseModel):
    source_class_id: UUID
    target_class_id: Optional[UUID] = None
    is_graduate: bool = False


class SectionMappingItem(BaseModel):
    source_section_id: UUID
    target_section_id: UUID


class StudentOverrideItem(BaseModel):
    student_id: UUID
    action: Literal["DETAIN", "TRANSFER", "WITHDRAW"]
    target_section_id: Optional[UUID] = None


class PromotionExecuteRequest(BaseModel):
    target_year_id: UUID
    grade_mappings: list[GradeMappingItem]
    section_mappings: list[SectionMappingItem]
    student_overrides: list[StudentOverrideItem] = []


class PromotionPreviewGradeMapping(BaseModel):
    source_class_id: UUID
    source_grade: str
    student_count: int
    suggested_target_class_id: Optional[UUID] = None
    suggested_target_grade: Optional[str] = None
    is_graduate: bool = False
    target_class_exists: bool = True


class PromotionPreviewSectionMapping(BaseModel):
    source_section_id: UUID
    source_section_name: str
    source_class_id: UUID
    source_grade: str
    student_count: int
    suggested_target_section_id: Optional[UUID] = None
    suggested_target_section_name: Optional[str] = None
    target_class_id: Optional[UUID] = None


class PromotionPreviewStudent(BaseModel):
    student_id: UUID
    full_name: str
    roll_number: str
    section_id: UUID
    section_name: str
    class_id: UUID
    grade: str
    attendance_pct: Optional[float] = None
    flagged_low_attendance: bool = False
    default_action: str = "PROMOTE"
    already_enrolled_in_target: bool = False
    source_status: str = "ACTIVE"


class PromotionPreviewResponse(BaseModel):
    source_year_id: UUID
    source_year_name: str
    target_year_id: UUID
    target_year_name: str
    grade_mappings: list[PromotionPreviewGradeMapping]
    section_mappings: list[PromotionPreviewSectionMapping]
    students: list[PromotionPreviewStudent]
    total_active_students: int
    duplicate_enrollment_count: int
    pending_leave_count: int
    low_attendance_threshold: float = 75.0


class PromotionSummary(BaseModel):
    total_reviewed: int
    promoted: int
    detained: int
    transferred: int
    graduated: int
    skipped_already_enrolled: int
    academic_records_created: int


class PromotionExecuteResponse(BaseModel):
    job_id: Optional[str] = None
    status: str
    summary: Optional[PromotionSummary] = None


class PromotionJobStatus(BaseModel):
    job_id: str
    status: str
    progress: int = 0
    total: int = 0
    summary: Optional[PromotionSummary] = None
    error: Optional[str] = None
