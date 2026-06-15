# Celery removed along with Redis. This stub keeps existing imports from crashing.
# Background tasks (notifications, report PDFs) can be migrated to asyncio tasks
# or a lightweight scheduler (APScheduler) in a future sprint.

class _StubCelery:
    def task(self, *args, **kwargs):
        def decorator(fn):
            return fn
        return decorator

    def send_task(self, *args, **kwargs):
        raise RuntimeError("Celery has been removed. Background tasks not available.")

celery_app = _StubCelery()
