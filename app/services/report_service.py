import uuid
from datetime import datetime

from app.core.redis import get_redis
from app.tasks.report_tasks import generate_report_pdf


async def queue_report_card(student_id: str, academic_year_id: str) -> dict:
    job_id = str(uuid.uuid4())
    redis = get_redis()
    key = f"report_job:{job_id}"
    await redis.setex(
        key,
        3600,
        f'{{"status":"QUEUED","result_url":null,"student_id":"{student_id}","academic_year_id":"{academic_year_id}","updated_at":"{datetime.utcnow().isoformat()}"}}',
    )
    generate_report_pdf.delay(job_id, student_id, academic_year_id)
    return {"job_id": job_id, "status": "QUEUED", "result_url": None, "updated_at": datetime.utcnow()}
