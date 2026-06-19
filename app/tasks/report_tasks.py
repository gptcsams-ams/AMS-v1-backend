from datetime import datetime


def generate_report_pdf(job_id: str, student_id: str, academic_year_id: str):
    # Celery removed — report PDF generation is a no-op stub.
    # Implement with asyncio background task or APScheduler in future sprint.
    return {
        "status": "PENDING",
        "job_id": job_id,
        "message": "Background task processing not available (Celery removed)",
    }
