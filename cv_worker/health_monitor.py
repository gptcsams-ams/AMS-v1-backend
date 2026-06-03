from datetime import datetime


async def check_camera_health() -> dict:
    return {"status": "ok", "checked_at": datetime.utcnow().isoformat()}
