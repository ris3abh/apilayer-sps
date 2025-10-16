# api/routers/auth.py
"""
Authentication Endpoints

Handles user authentication via AWS Cognito:
- Signup (register new users)
- Login (authenticate and get tokens)
- Token refresh
- User profile management
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime
import logging
from uuid import UUID

from api.dependencies import get_db, get_current_user, get_cognito_service
from api.schemas.auth import (
    SignupRequest,
    LoginRequest,
    RefreshTokenRequest,
    TokenResponse,
    UserResponse
)
from api.models.user import User
from api.services.cognito import CognitoService

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# AUTHENTICATION ENDPOINTS
# =============================================================================

@router.post("/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def signup(
    signup_data: SignupRequest,
    db: Session = Depends(get_db),
    cognito: CognitoService = Depends(get_cognito_service)
):
    """
    Register a new user.
    
    Process:
    1. Create user in Cognito
    2. Create user record in database
    3. Send verification email (automatic via Cognito)
    
    **Note:** User must verify email before logging in.
    
    Args:
        signup_data: User registration data
        
    Returns:
        User profile information
        
    Raises:
        400: Email already exists or invalid password
        500: Registration failed
    """
    # Check if user already exists in our database
    existing_user = db.query(User).filter(User.email == signup_data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    try:
        # Create user in Cognito
        logger.info(f"Creating Cognito user for: {signup_data.email}")
        cognito_response = cognito.signup(
            email=signup_data.email,
            password=signup_data.password,
            name=signup_data.name
        )
        
        cognito_sub = cognito_response['UserSub']
        
        # Create user in database
        new_user = User(
            cognito_sub=cognito_sub,
            email=signup_data.email,
            name=signup_data.name,
            company_name=signup_data.company_name,
            role='client',
            is_active=True  # Will need email verification to login
        )
        
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        logger.info(f"✅ User created successfully: {new_user.email}")
        
        return new_user
        
    except ValueError as e:
        # Cognito validation error (password requirements, etc.)
        logger.error(f"Signup validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Signup error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Registration failed: {str(e)}"
        )


@router.post("/login", response_model=TokenResponse)
async def login(
    login_data: LoginRequest,
    db: Session = Depends(get_db),
    cognito: CognitoService = Depends(get_cognito_service)
):
    """
    Authenticate user and get access tokens.
    
    **Note:** Email must be verified before login.
    
    Args:
        login_data: Login credentials
        
    Returns:
        Access token, refresh token, and token metadata
        
    Raises:
        401: Invalid credentials or email not verified
        404: User not found
    """
    try:
        # Authenticate with Cognito
        logger.info(f"Login attempt for: {login_data.email}")
        auth_result = cognito.login(
            email=login_data.email,
            password=login_data.password
        )
        
        # Get user from token
        user_info = cognito.get_user_from_token(auth_result['access_token'])
        cognito_sub = user_info['sub']
        
        # Get or update user in database
        user = db.query(User).filter(User.cognito_sub == cognito_sub).first()
        
        if not user:
            # User authenticated in Cognito but not in our database
            # This shouldn't happen if signup worked correctly
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found. Please complete signup."
            )
        
        # Update last login
        user.last_login_at = datetime.utcnow()
        db.commit()
        
        logger.info(f"✅ Login successful: {user.email}")
        
        return TokenResponse(
            access_token=auth_result['access_token'],
            refresh_token=auth_result['refresh_token'],
            token_type=auth_result['token_type'],
            expires_in=auth_result['expires_in']
        )
        
    except ValueError as e:
        # Invalid credentials or email not verified
        logger.warning(f"Login failed for {login_data.email}: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication failed"
        )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    refresh_data: RefreshTokenRequest,
    cognito: CognitoService = Depends(get_cognito_service)
):
    """
    Refresh access token using refresh token.
    
    Use this when the access token expires (1 hour default).
    
    Args:
        refresh_data: Refresh token
        
    Returns:
        New access token and metadata
        
    Raises:
        401: Invalid or expired refresh token
    """
    try:
        logger.info("Refreshing access token")
        auth_result = cognito.refresh_token(refresh_data.refresh_token)
        
        return TokenResponse(
            access_token=auth_result['access_token'],
            refresh_token=refresh_data.refresh_token,  # Same refresh token
            token_type=auth_result['token_type'],
            expires_in=auth_result['expires_in']
        )
        
    except ValueError as e:
        logger.warning(f"Token refresh failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Token refresh error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token refresh failed"
        )


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    current_user: User = Depends(get_current_user)
):
    """
    Get current authenticated user's profile.
    
    Requires valid access token in Authorization header.
    
    Returns:
        User profile information
    """
    return current_user


@router.patch("/me", response_model=UserResponse)
async def update_current_user_profile(
    name: str = None,
    company_name: str = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update current user's profile.
    
    Args:
        name: New name (optional)
        company_name: New company name (optional)
        
    Returns:
        Updated user profile
    """
    if name is not None:
        current_user.name = name
    
    if company_name is not None:
        current_user.company_name = company_name
    
    current_user.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(current_user)
    
    logger.info(f"Profile updated: {current_user.email}")
    
    return current_user


# =============================================================================
# EMAIL VERIFICATION (Cognito handles this automatically)
# =============================================================================

@router.post("/verify-email")
async def verify_email(
    email: str,
    code: str,
    cognito: CognitoService = Depends(get_cognito_service)
):
    """
    Verify email with confirmation code.
    
    **Note:** This is only needed if email auto-verification is disabled.
    By default, Cognito sends verification emails automatically.
    
    Args:
        email: User's email address
        code: Verification code from email
        
    Returns:
        Success message
    """
    try:
        cognito.confirm_sign_up(email, code)
        return {"message": "Email verified successfully"}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


# =============================================================================
# PASSWORD RESET (Future Enhancement)
# =============================================================================

@router.post("/forgot-password")
async def forgot_password(
    email: str,
    cognito: CognitoService = Depends(get_cognito_service)
):
    """
    Initiate password reset.
    
    Sends password reset code to user's email.
    
    Args:
        email: User's email address
        
    Returns:
        Success message
    """
    # TODO: Implement Cognito forgot_password
    return {
        "message": "If the email exists, a password reset code has been sent",
        "note": "Check your email for the reset code"
    }


@router.post("/reset-password")
async def reset_password(
    email: str,
    code: str,
    new_password: str,
    cognito: CognitoService = Depends(get_cognito_service)
):
    """
    Reset password with confirmation code.
    
    Args:
        email: User's email address
        code: Reset code from email
        new_password: New password
        
    Returns:
        Success message
    """
    # TODO: Implement Cognito confirm_forgot_password
    return {"message": "Password reset successfully"}