# api/models/activity.py
from sqlalchemy import Column, String, DateTime, Text, ForeignKey, JSON, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
import enum
from api.database import Base

class ActivityType(str, enum.Enum):
    TASK_START = "task_start"
    TASK_COMPLETE = "task_complete"
    AGENT_THINKING = "agent_thinking"
    TOOL_USAGE = "tool_usage"
    ERROR = "error"
    MESSAGE = "message"
    LLM_CALL = "llm_call"
    CREW_KICKOFF = "crew_kickoff"

class AgentActivity(Base):
    __tablename__ = "agent_activity"

    activity_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    execution_id = Column(UUID(as_uuid=True), ForeignKey('crew_executions.execution_id', ondelete='CASCADE'), nullable=False, index=True)
    agent_name = Column(String(100), nullable=False)
    activity_type = Column(Enum(ActivityType), nullable=False, index=True)
    message = Column(Text, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    activity_metadata = Column(JSON, default={})
    
    # Relationships
    execution = relationship("CrewExecution", backref="activities")