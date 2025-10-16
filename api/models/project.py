# api/models/project.py
from sqlalchemy import Column, String, DateTime, Text, ForeignKey, JSON, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
import enum
from api.database import Base

class ProjectStatus(str, enum.Enum):
    DRAFT = "draft"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    COMPLETED = "completed"
    ARCHIVED = "archived"

class Project(Base):
    __tablename__ = "projects"

    project_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id = Column(UUID(as_uuid=True), ForeignKey('clients.client_id', ondelete='CASCADE'), nullable=False, index=True)
    project_name = Column(String(255), nullable=False)
    topic = Column(Text, nullable=False)
    content_type = Column(String(50), nullable=False)  # blog, landing_page, local_article
    audience = Column(Text)
    ai_language_code = Column(String(100))
    status = Column(Enum(ProjectStatus), default=ProjectStatus.DRAFT, index=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.user_id'), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True))
    project_metadata = Column(JSON, default={})
    
    # Relationships
    client = relationship("Client", backref="projects")
    creator = relationship("User", backref="created_projects")