import asyncio
from datetime import datetime

from app.core.redis import init_redis, close_redis, get_redis
from app.tasks.celery_app import celery_app


@celery_app.task(name="app.tasks.report_tasks.generate_report_pdf")
def generate_report_pdf(job_id: str, student_id: str, academic_year_id: str):
    return asyncio.run(_generate_report_pdf(job_id, student_id, academic_year_id))


async def _generate_report_pdf(job_id: str, student_id: str, academic_year_id: str):
    await init_redis()
    redis = get_redis()
    key = f"report_job:{job_id}"
    try:
        fake_url = f"/media/reports/{job_id}.pdf"
        payload = {
            "status": "COMPLETED",
            "result_url": fake_url,
            "student_id": student_id,
            "academic_year_id": academic_year_id,
            "updated_at": datetime.utcnow().isoformat(),
        }
        await redis.setex(key, 3600, str(payload).replace("'", '"'))
        return payload
    except Exception as exc:
        payload = {
            "status": "FAILED",
            "result_url": None,
            "error": str(exc),
            "updated_at": datetime.utcnow().isoformat(),
        }
        await redis.setex(key, 3600, str(payload).replace("'", '"'))
        raise
    finally:
        await close_redis()
