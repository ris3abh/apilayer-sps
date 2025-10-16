# api/schemas/client.py
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from uuid import UUID

# Request schemas
class ClientCreate(BaseModel):
    client_name: str = Field(..., min_length=2, max_length=255)
    industry: Optional[str] = Field(None, max_length=100)
    target_audience: Optional[str] = None
    brand_guidelines: Optional[str] = None
    ai_language_code: Optional[str] = Field(None, max_length=100)

class ClientUpdate(BaseModel):
    client_name: Optional[str] = Field(None, min_length=2, max_length=255)
    industry: Optional[str] = Field(None, max_length=100)
    target_audience: Optional[str] = None
    brand_guidelines: Optional[str] = None
    ai_language_code: Optional[str] = Field(None, max_length=100)
    is_active: Optional[bool] = None

# Response schemas
class ClientResponse(BaseModel):
    client_id: UUID
    owner_id: UUID
    client_name: str
    industry: Optional[str]
    target_audience: Optional[str]
    brand_guidelines: Optional[str]
    ai_language_code: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class ClientListResponse(BaseModel):
    clients: list[ClientResponse]
    total: int