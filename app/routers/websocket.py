from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.core.security import decode_access_token
from app.core.redis import get_redis
import asyncio, logging

router = APIRouter()
log = logging.getLogger(__name__)


@router.websocket("/attendance/{section_id}")
async def attendance_ws(websocket: WebSocket, section_id: str, token: str):
    payload = decode_access_token(token)
    if not payload:
        await websocket.close(code=4001, reason="Unauthorized")
        return
    await websocket.accept()

    redis = get_redis()
    pubsub = redis.pubsub()
    channel = f"attendance:section:{section_id}"
    await pubsub.subscribe(channel)
    log.info(f"WS client subscribed to {channel}")

    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                await websocket.send_text(message["data"])
    except WebSocketDisconnect:
        pass
    except Exception as e:
        log.warning(f"WS error: {e}")
    finally:
        await pubsub.unsubscribe(channel)


@router.websocket("/cameras/health")
async def cameras_health_ws(websocket: WebSocket, token: str):
    payload = decode_access_token(token)
    if not payload or payload.get("role") not in ("SUPER_ADMIN", "ADMIN"):
        await websocket.close(code=4001)
        return
    await websocket.accept()

    redis = get_redis()
    pubsub = redis.pubsub()
    await pubsub.psubscribe("camera:health:*")

    try:
        async for message in pubsub.listen():
            if message["type"] == "pmessage":
                await websocket.send_text(message["data"])
    except WebSocketDisconnect:
        pass
    finally:
        await pubsub.punsubscribe("camera:health:*")


@router.websocket("/notifications/{user_id}")
async def notifications_ws(websocket: WebSocket, user_id: str, token: str):
    payload = decode_access_token(token)
    if not payload or payload.get("sub") != user_id:
        await websocket.close(code=4001)
        return
    await websocket.accept()

    redis = get_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe(f"notifications:user:{user_id}")

    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                await websocket.send_text(message["data"])
    except WebSocketDisconnect:
        pass
    finally:
        await pubsub.unsubscribe(f"notifications:user:{user_id}")
