from sqlalchemy import Column, String, Integer, TIMESTAMP, ForeignKey, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from app.core.database import Base

class Classroom(Base):
    __tablename__ = "classrooms"
    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id  = Column(UUID(as_uuid=True),
                        ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)
    room_name  = Column(String(100), nullable=False)
    floor      = Column(String(50))
    building   = Column(String(100))
    capacity   = Column(Integer)
    created_at = Column(TIMESTAMP, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("branch_id", "room_name", name="uq_room_per_branch"),
        Index("idx_classroom_branch_id", "branch_id"),
    )
