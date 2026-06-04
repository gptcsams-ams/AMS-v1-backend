from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_admin
from app.models.audit_log import AuditLog
from app.schemas.audit import AuditLogResponse

router = APIRouter()


@router.get("", response_model=list[AuditLogResponse])
async def list_audit_logs(
    user_id: UUID | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    _: object = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc())
    if user_id:
        stmt = stmt.where(AuditLog.user_id == user_id)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    rows = await db.execute(stmt)
    return list(rows.scalars().all())
