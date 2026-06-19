from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.redis import close_redis, init_redis
from app.middleware.audit_middleware import AuditMiddleware
from app.middleware.if_modified_since_middleware import IfModifiedSinceMiddleware
from app.middleware.rate_limit_middleware import RateLimitMiddleware
from app.routers import (
    parent_portal,
    academic_years, attendance, audit, auth, branding, branches,
    calendar, cameras, classes, detections, enrollments, leaves,
    mobile, notifications, parents, ptm, reports, school, sections,
    students, subjects, teachers, timetable, websocket,
)

PREFIX = "/api/v1"
log    = logging.getLogger("startup")


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_redis()
    try:
        yield
    finally:
        await close_redis()


app = FastAPI(title="AMS Backend", version="2.0.0", lifespan=lifespan)
origins = ["*"] if settings.ALLOWED_ORIGINS == "*" else [o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.add_middleware(RateLimitMiddleware)
app.add_middleware(AuditMiddleware)
app.add_middleware(IfModifiedSinceMiddleware)

for r, t in [
    (auth.router, "Auth"), (branding.router, "Branding"), (school.router, "School"), (branches.router, "Branches"),
    (academic_years.router, "AcademicYears"), (classes.router, "Classes"), (sections.router, "Sections"), (subjects.router, "Subjects"),
    (students.router, "Students"), (enrollments.router, "Enrollments"), (teachers.router, "Teachers"), (parents.router, "Parents"),
    (timetable.router, "Timetable"), (attendance.router, "Attendance"), (cameras.router, "Cameras"), (detections.router, "Detections"),
    (ptm.router, "PTM"), (leaves.router, "Leaves"), (notifications.router, "Notifications"), (calendar.router, "Calendar"),
    (reports.router, "Reports"), (audit.router, "Audit"), (mobile.router, "Mobile"),(leaves.router, "Leaves"),
    (notifications.router, "Notifications"), (parent_portal.router, "Parent Portal")
]:
    app.include_router(r, prefix="/api/v1", tags=[t])

app.include_router(websocket.router, prefix="/ws", tags=["WebSocket"])


@app.get("/health")
async def health_check() -> dict:
    return {"status": "ok"}
