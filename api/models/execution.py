# api/models/execution.py
from sqlalchemy import Column, String, Integer, DateTime, Text, ForeignKey, JSON, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
import enum
from api.database import Base

class ExecutionStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class CrewExecution(Base):
    __tablename__ = "crew_executions"

    execution_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey('projects.project_id', ondelete='CASCADE'), nullable=False, index=True)
    workflow_mode = Column(String(50), nullable=False)  # creation, revision
    status = Column(Enum(ExecutionStatus), default=ExecutionStatus.PENDING, index=True)
    crewai_execution_id = Column(String(255), index=True)  # kickoff_id from CrewAI
    started_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    completed_at = Column(DateTime(timezone=True))
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.user_id'), nullable=False)
    metrics = Column(JSON, default={})  # token usage, costs, duration
    
    # Relationships
    project = relationship("Project", backref="executions")
    creator = relationship("User", backref="started_executions")