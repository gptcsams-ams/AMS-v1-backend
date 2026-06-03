from app.tasks.celery_app import celery_app


@celery_app.task(name="app.tasks.maintenance_tasks.compute_defaulters")
def compute_defaulters():
    return {"status": "ok"}


@celery_app.task(name="app.tasks.maintenance_tasks.auto_retrain_embeddings")
def auto_retrain_embeddings():
    return {"status": "ok"}


@celery_app.task(name="app.tasks.maintenance_tasks.check_embedding_freshness")
def check_embedding_freshness():
    return {"status": "ok"}


@celery_app.task(name="app.tasks.maintenance_tasks.prune_camera_health_logs")
def prune_camera_health_logs():
    return {"status": "ok"}


@celery_app.task(name="app.tasks.maintenance_tasks.prune_old_notifications")
def prune_old_notifications():
    return {"status": "ok"}


@celery_app.task(name="app.tasks.maintenance_tasks.trigger_backup")
def trigger_backup():
    return {"status": "ok"}
