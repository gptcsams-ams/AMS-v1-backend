from app.models.academic_class import AcademicClass
from app.models.academic_record import AcademicRecord
from app.models.academic_year import AcademicYear
from app.models.attendance import Attendance
from app.models.attendance_window import AttendanceWindow
from app.models.audit_log import AuditLog
from app.models.branch import Branch
from app.models.branding import Branding
from app.models.camera import Camera
from app.models.camera_health_log import CameraHealthLog
from app.models.classroom import Classroom
from app.models.detection import Detection
from app.models.leave_request import LeaveRequest
from app.models.notification import Notification
from app.models.notification_template import NotificationTemplate
from app.models.parent import Parent
from app.models.period_slot import PeriodSlot
from app.models.ptm_record import PTMRecord
from app.models.school import School
from app.models.school_calendar import SchoolCalendar
from app.models.section import Section
from app.models.student import Student
from app.models.student_enrollment import StudentEnrollment
from app.models.student_face import StudentFace
from app.models.student_parent import StudentParent
from app.models.subject import Subject
from app.models.teacher_profile import TeacherProfile
from app.models.teacher_subject_eligibility import TeacherSubjectEligibility
from app.models.timetable_entry import TimetableEntry
from app.models.timetable_frequency_target import TimetableFrequencyTarget
from app.models.user import User

__all__ = [
    "AcademicClass",
    "AcademicRecord",
    "AcademicYear",
    "Attendance",
    "AttendanceWindow",
    "AuditLog",
    "Branch",
    "Branding",
    "Camera",
    "CameraHealthLog",
    "Classroom",
    "Detection",
    "LeaveRequest",
    "Notification",
    "NotificationTemplate",
    "Parent",
    "PeriodSlot",
    "PTMRecord",
    "School",
    "SchoolCalendar",
    "Section",
    "Student",
    "StudentEnrollment",
    "StudentFace",
    "StudentParent",
    "Subject",
    "TeacherProfile",
    "TeacherSubjectEligibility",
    "TimetableEntry",
    "TimetableFrequencyTarget",
    "User",
]
