from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.redis import close_redis, init_redis
from app.middleware.audit_middleware import AuditMiddleware
from app.middleware.if_modified_since_middleware import IfModifiedSinceMiddleware
from app.middleware.rate_limit_middleware import RateLimitMiddleware
from app.routers import (
    academic_years, attendance, audit, auth, branding, branches,
    calendar, cameras, classes, detections, enrollments, leaves,
    mobile, notifications, parents, reports, school, sections,
    students, subjects, teachers, timetable, websocket,
)

PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_redis()
    try:
        yield
    finally:
        await close_redis()


app = FastAPI(title="AMS Backend", version="2.0.0", lifespan=lifespan)

origins = ["*"] if settings.ALLOWED_ORIGINS == "*" else [
    o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(AuditMiddleware)
app.add_middleware(IfModifiedSinceMiddleware)

# Auth — must come before the generic PREFIX includes
app.include_router(auth.router,           prefix=f"{PREFIX}/auth",           tags=["Auth"])
app.include_router(branding.router,       prefix=f"{PREFIX}/branding",        tags=["Branding"])
app.include_router(school.router,         prefix=f"{PREFIX}/school",          tags=["School"])
app.include_router(branches.router,       prefix=f"{PREFIX}/branches",        tags=["Branches"])
app.include_router(academic_years.router, prefix=f"{PREFIX}/academic-years",  tags=["AcademicYears"])
app.include_router(classes.router,        prefix=f"{PREFIX}/classes",         tags=["Classes"])
app.include_router(sections.router,       prefix=f"{PREFIX}/sections",        tags=["Sections"])
app.include_router(subjects.router,       prefix=f"{PREFIX}/subjects",        tags=["Subjects"])
app.include_router(students.router,       prefix=f"{PREFIX}/students",        tags=["Students"])
app.include_router(enrollments.router,    prefix=f"{PREFIX}/enrollments",     tags=["Enrollments"])
app.include_router(teachers.router,       prefix=f"{PREFIX}/teachers",        tags=["Teachers"])
app.include_router(parents.router,        prefix=f"{PREFIX}/parents",         tags=["Parents"])
app.include_router(timetable.router,      prefix=f"{PREFIX}/timetable",       tags=["Timetable"])
app.include_router(attendance.router,     prefix=f"{PREFIX}",                 tags=["Attendance"])
app.include_router(cameras.router,        prefix=f"{PREFIX}/cameras",         tags=["Cameras"])
app.include_router(detections.router,     prefix=f"{PREFIX}/detections",      tags=["Detections"])
app.include_router(leaves.router,         prefix=f"{PREFIX}/leaves",          tags=["Leaves"])
app.include_router(notifications.router,  prefix=f"{PREFIX}/notifications",   tags=["Notifications"])
app.include_router(calendar.router,       prefix=f"{PREFIX}/calendar",        tags=["Calendar"])
app.include_router(reports.router,        prefix=f"{PREFIX}/reports",         tags=["Reports"])
app.include_router(audit.router,          prefix=f"{PREFIX}/audit",           tags=["Audit"])
app.include_router(mobile.router,         prefix=f"{PREFIX}/mobile",          tags=["Mobile"])
app.include_router(websocket.router,      prefix="/ws",                        tags=["WebSocket"])


@app.get("/health")
async def health_check() -> dict:
    return {"status": "ok", "version": "2.0.0"}
