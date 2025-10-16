# api/dependencies.py - Update the authentication section
import jwt
from jwt.exceptions import PyJWTError as JWTError
from fastapi import Depends, HTTPException, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from api.database import SessionLocal
from api.models.user import User
from api.config import settings
import logging

logger = logging.getLogger(__name__)

security = HTTPBearer()


# =============================================================================
# DATABASE
# =============================================================================

def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =============================================================================
# AUTHENTICATION
# =============================================================================

def decode_token(token: str) -> dict:
    """
    Decode JWT token (works for both Cognito and mock tokens).
    
    In development (mock mode): verifies with JWT_SECRET
    In production (Cognito): should verify with Cognito public keys
    
    Args:
        token: JWT token string
        
    Returns:
        Decoded token payload
        
    Raises:
        HTTPException: If token is invalid
    """
    try:
        # In mock mode or development, verify with JWT_SECRET
        if settings.USE_MOCK_AUTH:
            payload = jwt.decode(
                token,
                settings.JWT_SECRET,
                options={"verify_exp": False, "verify_iat": False},
                algorithms=[settings.JWT_ALGORITHM]
            )
            return payload
        
        # In production with real Cognito
        # TODO: Implement proper Cognito JWT verification with public keys
        # For now, decode without verification (SECURITY RISK - FIX BEFORE PRODUCTION)
        payload = jwt.decode(
            token,
            options={"verify_signature": False}
        )
        return payload
        
    except jwt.ExpiredSignatureError:
        logger.error("Token has expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTError as e:
        logger.error(f"JWT decode error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user_cognito_sub(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> str:
    """
    Extract Cognito sub (user ID) from JWT token.
    
    Args:
        credentials: HTTP Bearer credentials
        
    Returns:
        Cognito sub (unique user identifier)
        
    Raises:
        HTTPException: If token is invalid or sub not found
    """
    token = credentials.credentials
    payload = decode_token(token)
    
    cognito_sub = payload.get("sub")
    if not cognito_sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return cognito_sub


async def get_current_user(
    cognito_sub: str = Depends(get_current_user_cognito_sub),
    db: Session = Depends(get_db)
) -> User:
    """
    Get current authenticated user from database.
    
    Args:
        cognito_sub: Cognito user ID from JWT token
        db: Database session
        
    Returns:
        User object from database
        
    Raises:
        HTTPException: If user not found or inactive
    """
    user = db.query(User).filter(User.cognito_sub == cognito_sub).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )
    
    return user

# =============================================================================
# WEBHOOK AUTHENTICATION
# =============================================================================

async def verify_webhook_token(
    authorization: str = Header(...)
) -> bool:
    """
    Verify webhook authentication token from CrewAI.
    
    CrewAI sends webhooks with Bearer token authentication:
    Authorization: Bearer {WEBHOOK_SECRET_TOKEN}
    
    Reference: https://docs.crewai.com/concepts/webhook-streaming#usage
    
    Args:
        authorization: Authorization header from request
        
    Returns:
        True if token is valid
        
    Raises:
        HTTPException: If token is invalid or missing
    """
    if not authorization:
        logger.warning("Webhook received without Authorization header")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header"
        )
    
    if not authorization.startswith("Bearer "):
        logger.warning(f"Webhook received with invalid auth format: {authorization[:20]}...")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization format. Expected: Bearer <token>"
        )
    
    token = authorization.replace("Bearer ", "")
    
    if token != settings.WEBHOOK_SECRET_TOKEN:
        logger.warning("Webhook received with invalid token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook token"
        )
    
    logger.debug("✅ Webhook authentication successful")
    return True


# =============================================================================
# SERVICE DEPENDENCIES
# =============================================================================

def get_s3_service():
    """Get S3 service instance"""
    from api.services.s3 import S3Service
    return S3Service()


def get_crewai_service():
    """Get CrewAI service instance"""
    from api.services.crewai import CrewAIService
    return CrewAIService()


def get_cognito_service():
    """Get Cognito service instance"""
    from api.services.cognito import CognitoService
    return CognitoService()


# =============================================================================
# PAGINATION
# =============================================================================

class PaginationParams:
    """Reusable pagination parameters"""
    
    def __init__(
        self,
        page: int = 1,
        page_size: int = 20,
    ):
        self.page = max(1, page)
        self.page_size = min(100, max(1, page_size))
        self.skip = (self.page - 1) * self.page_size
        self.limit = self.page_size


# =============================================================================
# ROLE-BASED ACCESS CONTROL
# =============================================================================

class RoleChecker:
    """Dependency to check user roles"""
    
    def __init__(self, allowed_roles: list):
        self.allowed_roles = allowed_roles
    
    def __call__(self, user: User = Depends(get_current_user)):
        if user.role not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"User role '{user.role}' not authorized for this action"
            )
        return user


# Predefined role checkers
require_admin = RoleChecker(['admin'])
require_client = RoleChecker(['client', 'admin'])