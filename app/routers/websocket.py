"""WebSocket endpoints — /ws/*"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.core.security import decode_access_token
from app.ws.connection_manager import notification_manager
import logging

router = APIRouter()
log = logging.getLogger(__name__)


@router.websocket("/attendance/{section_id}")
async def attendance_ws(websocket: WebSocket, section_id: str, token: str):
    """Real-time attendance detection events for a section."""
    payload = decode_access_token(token)
    if not payload:
        await websocket.close(code=4001, reason="Unauthorized")
        return
    # Use a virtual user_id keyed by section for the attendance stream
    virtual_id = f"section:{section_id}"
    await notification_manager.connect(virtual_id, websocket)
    try:
        while True:
            # Keep connection alive; events are pushed server-side
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception as e:
        log.warning("attendance WS error section=%s: %s", section_id, e)
    finally:
        notification_manager.disconnect(virtual_id, websocket)


@router.websocket("/cameras/health")
async def cameras_health_ws(websocket: WebSocket, token: str):
    """Real-time camera health status stream."""
    payload = decode_access_token(token)
    if not payload or payload.get("role") not in ("SUPER_ADMIN", "ADMIN"):
        await websocket.close(code=4001)
        return
    virtual_id = f"cameras:health:{payload.get('sub')}"
    await notification_manager.connect(virtual_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        notification_manager.disconnect(virtual_id, websocket)


@router.websocket("/notifications/{user_id}")
async def notifications_ws(websocket: WebSocket, user_id: str, token: str):
    """Real-time notification push for a user (parent/admin)."""
    payload = decode_access_token(token)
    if not payload or payload.get("sub") != user_id:
        await websocket.close(code=4001)
        return
    await notification_manager.connect(user_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        notification_manager.disconnect(user_id, websocket)
