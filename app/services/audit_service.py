from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession


async def log_audit(
    db: AsyncSession,
    actor_id: str,
    action: str,
    entity_type: str,
    entity_id: Optional[str] = None,
    payload: Optional[dict[str, Any]] = None,
) -> None:
    # Placeholder hook; concrete audit write is implemented in later sprint.
    _ = (db, actor_id, action, entity_type, entity_id, payload)
