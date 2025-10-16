# api/models/checkpoint.py
from sqlalchemy import Column, String, DateTime, Text, ForeignKey, JSON, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
import enum
from api.database import Base

class CheckpointType(str, enum.Enum):
    BRAND_VOICE = "brand_voice"
    STYLE_COMPLIANCE = "style_compliance"
    FINAL_QA = "final_qa"

class CheckpointStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    REVISION_REQUESTED = "revision_requested"

class HITLCheckpoint(Base):
    __tablename__ = "hitl_checkpoints"

    checkpoint_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    execution_id = Column(UUID(as_uuid=True), ForeignKey('crew_executions.execution_id', ondelete='CASCADE'), nullable=False, index=True)
    checkpoint_type = Column(Enum(CheckpointType), nullable=False, index=True)
    task_id = Column(String(255))  # Task ID from CrewAI
    status = Column(Enum(CheckpointStatus), default=CheckpointStatus.PENDING, index=True)
    content = Column(Text, nullable=False)  # Content to review
    reviewer_feedback = Column(Text)
    reviewed_by = Column(UUID(as_uuid=True), ForeignKey('users.user_id'))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    reviewed_at = Column(DateTime(timezone=True))
    checkpoint_metadata = Column(JSON, default={})
    
    # Relationships
    execution = relationship("CrewExecution", backref="checkpoints")
    reviewer = relationship("User", backref="reviewed_checkpoints")