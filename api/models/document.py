# api/models/document.py
from sqlalchemy import Column, String, Integer, BigInteger, DateTime, ForeignKey, JSON, Enum, UniqueConstraint, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
import enum
from api.database import Base

class DocumentType(str, enum.Enum):
    BRAND_VOICE = "brand_voice"
    STYLE_GUIDE = "style_guide"
    SAMPLE_CONTENT = "sample_content"
    MARKETING_MATERIAL = "marketing_material"
    PREVIOUS_WORK = "previous_work"

class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint('client_id', 'document_type', 'file_name', 'version', name='_client_doc_version_uc'),
    )

    document_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id = Column(UUID(as_uuid=True), ForeignKey('clients.client_id', ondelete='CASCADE'), nullable=False, index=True)
    document_type = Column(Enum(DocumentType), nullable=False, index=True)
    file_name = Column(String(255), nullable=False)
    s3_bucket = Column(String(255), nullable=False)
    s3_key = Column(Text, nullable=False, index=True)
    file_size = Column(BigInteger)
    mime_type = Column(String(100))
    version = Column(Integer, default=1)
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey('users.user_id'), nullable=False)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())
    document_metadata = Column(JSON, default={})
    
    # Relationships
    client = relationship("Client", backref="documents")
    uploader = relationship("User", backref="uploaded_documents")