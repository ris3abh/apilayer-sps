# api/schemas/project.py
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from uuid import UUID
from api.models.project import ProjectStatus

# Request schemas
class ProjectCreate(BaseModel):
    client_id: UUID
    project_name: str = Field(..., min_length=2, max_length=255)
    topic: str = Field(..., min_length=10)
    content_type: str = Field(..., pattern="^(blog|landing_page|local_article)$")
    audience: Optional[str] = None
    ai_language_code: Optional[str] = Field(None, max_length=100)

class ProjectUpdate(BaseModel):
    project_name: Optional[str] = Field(None, min_length=2, max_length=255)
    topic: Optional[str] = Field(None, min_length=10)
    content_type: Optional[str] = Field(None, pattern="^(blog|landing_page|local_article)$")
    audience: Optional[str] = None
    ai_language_code: Optional[str] = Field(None, max_length=100)
    status: Optional[ProjectStatus] = None

# Response schemas
class ProjectResponse(BaseModel):
    project_id: UUID
    client_id: UUID
    project_name: str
    topic: str
    content_type: str
    audience: Optional[str]
    ai_language_code: Optional[str]
    status: ProjectStatus
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime]
    
    class Config:
        from_attributes = True

class ProjectListResponse(BaseModel):
    projects: list[ProjectResponse]
    total: int