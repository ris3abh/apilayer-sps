# api/models/client.py
from sqlalchemy import Column, String, Boolean, DateTime, Text, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
from api.database import Base

class Client(Base):
    __tablename__ = "clients"

    client_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id = Column(UUID(as_uuid=True), ForeignKey('users.user_id'), nullable=False, index=True)
    client_name = Column(String(255), nullable=False)
    industry = Column(String(100))
    target_audience = Column(Text)
    brand_guidelines = Column(Text)
    ai_language_code = Column(String(100))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    # Renamed from 'metadata' to avoid SQLAlchemy reserved name conflict
    client_metadata = Column(JSON, default={})
    
    # Relationships
    owner = relationship("User", backref="clients")