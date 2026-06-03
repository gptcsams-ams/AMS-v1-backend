from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "ams",
    broker=settings.REDIS_URL.replace("/0", "/1"),
    backend=settings.REDIS_URL.replace("/0", "/2"),
    include=[
        "app.tasks.notification_tasks",
        "app.tasks.report_tasks",
        "app.tasks.maintenance_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_routes={
        "app.tasks.notification_tasks.*": {"queue": "notify"},
        "app.tasks.report_tasks.*": {"queue": "reports"},
        "app.tasks.maintenance_tasks.*": {"queue": "maintenance"},
    },
    beat_schedule={
        "defaulter-check": {"task": "app.tasks.maintenance_tasks.compute_defaulters", "schedule": crontab(hour=18, minute=0)},
        "auto-retrain": {"task": "app.tasks.maintenance_tasks.auto_retrain_embeddings", "schedule": crontab(hour=2, minute=0)},
        "embedding-freshness": {"task": "app.tasks.maintenance_tasks.check_embedding_freshness", "schedule": crontab(hour=6, minute=0, day_of_week="monday")},
        "notification-retry": {"task": "app.tasks.notification_tasks.retry_failed", "schedule": crontab(minute="*/15")},
        "prune-camera-logs": {"task": "app.tasks.maintenance_tasks.prune_camera_health_logs", "schedule": crontab(hour=3, minute=0)},
        "prune-notifications": {"task": "app.tasks.maintenance_tasks.prune_old_notifications", "schedule": crontab(hour=3, minute=30)},
        "nightly-backup": {"task": "app.tasks.maintenance_tasks.trigger_backup", "schedule": crontab(hour=1, minute=0)},
    },
)
