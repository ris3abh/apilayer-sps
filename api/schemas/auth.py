# api/schemas/auth.py
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime
from uuid import UUID

# Request schemas
class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=12, description="Min 12 chars, must include uppercase, lowercase, number, symbol")
    name: str = Field(..., min_length=2)
    company_name: Optional[str] = None

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class RefreshTokenRequest(BaseModel):
    refresh_token: str

# Response schemas
class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds

class UserResponse(BaseModel):
    user_id: UUID
    email: str
    name: str
    company_name: Optional[str]
    role: str
    is_active: bool
    created_at: datetime
    last_login_at: Optional[datetime]
    
    class Config:
        from_attributes = True