import asyncio
import json
from datetime import datetime

from app.core.database import AsyncSessionLocal
from app.core.redis import close_redis, get_redis, init_redis
from app.schemas.promotion import PromotionExecuteRequest, PromotionSummary
from app.services.promotion_service import execute_promotion
from app.tasks.celery_app import celery_app


@celery_app.task(name="app.tasks.promotion_tasks.run_promotion")
def run_promotion(job_id: str, source_year_id: str, payload_dict: dict, generated_by: str | None):
    return asyncio.run(_run_promotion(job_id, source_year_id, payload_dict, generated_by))


async def _run_promotion(job_id: str, source_year_id: str, payload_dict: dict, generated_by: str | None):
    await init_redis()
    redis = get_redis()
    key = f"promotion_job:{job_id}"
    try:
        await redis.setex(
            key,
            7200,
            json.dumps(
                {
                    "status": "RUNNING",
                    "progress": 0,
                    "total": 0,
                    "summary": None,
                    "error": None,
                    "updated_at": datetime.utcnow().isoformat(),
                }
            ),
        )
        payload = PromotionExecuteRequest.model_validate(payload_dict)
        async with AsyncSessionLocal() as db:
            summary = await execute_promotion(
                db,
                __import__("uuid").UUID(source_year_id),
                payload,
                __import__("uuid").UUID(generated_by) if generated_by else None,
            )
        result = {
            "status": "COMPLETED",
            "progress": summary.total_reviewed,
            "total": summary.total_reviewed,
            "summary": summary.model_dump(),
            "error": None,
            "updated_at": datetime.utcnow().isoformat(),
        }
        await redis.setex(key, 7200, json.dumps(result))
        return result
    except Exception as exc:
        result = {
            "status": "FAILED",
            "progress": 0,
            "total": 0,
            "summary": None,
            "error": str(exc),
            "updated_at": datetime.utcnow().isoformat(),
        }
        await redis.setex(key, 7200, json.dumps(result))
        raise
    finally:
        await close_redis()
