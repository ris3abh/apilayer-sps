# api/schemas/document.py
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from uuid import UUID
from api.models.document import DocumentType

# Request schemas
class DocumentUploadRequest(BaseModel):
    """Request to get presigned URL for upload"""
    file_name: str = Field(..., min_length=1, max_length=255)
    document_type: DocumentType
    mime_type: str = Field(..., max_length=100)
    file_size: int = Field(..., gt=0, description="File size in bytes")

class DocumentUploadResponse(BaseModel):
    """Response with presigned URL for upload"""
    document_id: UUID
    presigned_url: str
    s3_key: str
    expires_in: int = 3600  # seconds

# Response schemas
class DocumentResponse(BaseModel):
    document_id: UUID
    client_id: UUID
    document_type: DocumentType
    file_name: str
    s3_bucket: str
    s3_key: str
    file_size: Optional[int]
    mime_type: Optional[str]
    version: int
    uploaded_by: UUID
    uploaded_at: datetime
    
    class Config:
        from_attributes = True

class DocumentDownloadResponse(BaseModel):
    document_id: UUID
    file_name: str
    presigned_url: str
    expires_in: int = 3600

class DocumentListResponse(BaseModel):
    documents: list[DocumentResponse]
    total: int