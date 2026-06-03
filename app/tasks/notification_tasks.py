import asyncio

from app.tasks.celery_app import celery_app
from app.services.notification_service import dispatch_notification


@celery_app.task(name="app.tasks.notification_tasks.send_one")
def send_one(channel: str, to: str, message: str, subject: str | None = None):
    return asyncio.run(dispatch_notification(channel, to, message, subject))


@celery_app.task(name="app.tasks.notification_tasks.retry_failed")
def retry_failed():
    return {"status": "ok", "retried": 0}
