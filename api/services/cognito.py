# api/services/cognito.py
import boto3
import jwt
from datetime import datetime, timedelta
from typing import Dict, Optional
from botocore.exceptions import ClientError
from api.config import settings
import logging

logger = logging.getLogger(__name__)


class CognitoService:
    """
    AWS Cognito authentication service.
    Supports both real Cognito and mock mode for local development.
    """
    
    def __init__(self):
        self.mock_mode = settings.USE_MOCK_AUTH
        
        if self.mock_mode:
            logger.warning("🔧 Running in MOCK AUTH mode - for development only!")
            self.user_pool_id = "mock-pool-id"
            self.client_id = "mock-client-id"
            self.client = None
        else:
            # Real Cognito setup
            self.client = boto3.client('cognito-idp', region_name=settings.AWS_REGION)
            self.user_pool_id = self._get_user_pool_id()
            self.client_id = self._get_client_id()
    
    def _get_user_pool_id(self) -> str:
        """Get User Pool ID from config or CloudFormation"""
        # First check if hardcoded in env
        if settings.COGNITO_USER_POOL_ID:
            return settings.COGNITO_USER_POOL_ID
        
        # Try CloudFormation
        cfn = boto3.client('cloudformation', region_name=settings.AWS_REGION)
        try:
            response = cfn.describe_stacks(StackName='spinscribe-production')
            for output in response['Stacks'][0]['Outputs']:
                if output['OutputKey'] == 'UserPoolId':
                    return output['OutputValue']
        except Exception as e:
            logger.warning(f"Could not get User Pool from CloudFormation: {e}")
        
        # Fallback - list user pools
        try:
            pools = self.client.list_user_pools(MaxResults=50)
            for pool in pools['UserPools']:
                if 'spinscribe' in pool['Name'].lower():
                    return pool['Id']
        except Exception as e:
            logger.error(f"Could not list user pools: {e}")
        
        raise Exception("User Pool not found. Set COGNITO_USER_POOL_ID in .env or use USE_MOCK_AUTH=true")
    
    def _get_client_id(self) -> str:
        """Get User Pool Client ID from config or CloudFormation"""
        # First check if hardcoded in env
        if settings.COGNITO_CLIENT_ID:
            return settings.COGNITO_CLIENT_ID
        
        # Try CloudFormation
        cfn = boto3.client('cloudformation', region_name=settings.AWS_REGION)
        try:
            response = cfn.describe_stacks(StackName='spinscribe-production')
            for output in response['Stacks'][0]['Outputs']:
                if output['OutputKey'] == 'UserPoolClientId':
                    return output['OutputValue']
        except Exception as e:
            logger.warning(f"Could not get Client ID from CloudFormation: {e}")
        
        raise Exception("Client ID not found. Set COGNITO_CLIENT_ID in .env or use USE_MOCK_AUTH=true")
    
    # =============================================================================
    # MOCK AUTH METHODS (Development Only)
    # =============================================================================
    
    def _mock_signup(self, email: str, password: str, name: str) -> Dict:
        """Mock signup for local development"""
        logger.info(f"🔧 MOCK: Signing up user {email}")
        return {
            'UserSub': f'mock-sub-{email}',
            'UserConfirmed': True
        }
    
    def _mock_login(self, email: str, password: str) -> Dict:
        """Mock login for local development"""
        logger.info(f"🔧 MOCK: Logging in user {email}")
        
        # Create a mock JWT token
        payload = {
            'sub': f'mock-sub-{email}',
            'email': email,
            'exp': datetime.utcnow() + timedelta(hours=1),
            'iat': datetime.utcnow()
        }
        
        access_token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
        refresh_token = jwt.encode(
            {**payload, 'exp': datetime.utcnow() + timedelta(days=30)},
            settings.JWT_SECRET,
            algorithm=settings.JWT_ALGORITHM
        )
        
        return {
            'access_token': access_token,
            'refresh_token': refresh_token,
            'token_type': 'Bearer',
            'expires_in': 3600
        }
    
    def _mock_get_user_from_token(self, access_token: str) -> Dict:
        """Mock get user from token"""
        try:
            payload = jwt.decode(
                access_token,
                settings.JWT_SECRET,
                algorithms=[settings.JWT_ALGORITHM]
            )
            return {
                'sub': payload['sub'],
                'email': payload['email']
            }
        except jwt.ExpiredSignatureError:
            raise ValueError("Token has expired")
        except jwt.InvalidTokenError:
            raise ValueError("Invalid token")
    
    def _mock_refresh_token(self, refresh_token: str) -> Dict:
        """Mock refresh token"""
        try:
            payload = jwt.decode(
                refresh_token,
                settings.JWT_SECRET,
                algorithms=[settings.JWT_ALGORITHM]
            )
            
            # Generate new access token
            new_payload = {
                'sub': payload['sub'],
                'email': payload['email'],
                'exp': datetime.utcnow() + timedelta(hours=1),
                'iat': datetime.utcnow()
            }
            
            access_token = jwt.encode(new_payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
            
            return {
                'access_token': access_token,
                'token_type': 'Bearer',
                'expires_in': 3600
            }
        except jwt.ExpiredSignatureError:
            raise ValueError("Refresh token has expired")
        except jwt.InvalidTokenError:
            raise ValueError("Invalid refresh token")
    
    # =============================================================================
    # PUBLIC API (Auto-switches between mock and real)
    # =============================================================================
    
    def signup(self, email: str, password: str, name: str) -> Dict:
        """Register a new user"""
        if self.mock_mode:
            return self._mock_signup(email, password, name)
        
        try:
            response = self.client.sign_up(
                ClientId=self.client_id,
                Username=email,
                Password=password,
                UserAttributes=[
                    {'Name': 'email', 'Value': email},
                    {'Name': 'name', 'Value': name}
                ]
            )
            return {
                'UserSub': response['UserSub'],
                'UserConfirmed': response.get('UserConfirmed', False)
            }
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'UsernameExistsException':
                raise ValueError("User with this email already exists")
            elif error_code == 'InvalidPasswordException':
                raise ValueError("Password does not meet requirements")
            else:
                raise ValueError(f"Signup failed: {e.response['Error']['Message']}")
    
    def login(self, email: str, password: str) -> Dict:
        """Authenticate user and return tokens"""
        if self.mock_mode:
            return self._mock_login(email, password)
        
        try:
            response = self.client.initiate_auth(
                ClientId=self.client_id,
                AuthFlow='USER_PASSWORD_AUTH',
                AuthParameters={
                    'USERNAME': email,
                    'PASSWORD': password
                }
            )
            
            auth_result = response['AuthenticationResult']
            return {
                'access_token': auth_result['AccessToken'],
                'refresh_token': auth_result['RefreshToken'],
                'token_type': 'Bearer',
                'expires_in': auth_result['ExpiresIn']
            }
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'NotAuthorizedException':
                raise ValueError("Invalid email or password")
            elif error_code == 'UserNotConfirmedException':
                raise ValueError("Email not verified. Please check your email for verification code.")
            else:
                raise ValueError(f"Login failed: {e.response['Error']['Message']}")
    
    def get_user_from_token(self, access_token: str) -> Dict:
        """Get user details from access token"""
        if self.mock_mode:
            return self._mock_get_user_from_token(access_token)
        
        try:
            response = self.client.get_user(AccessToken=access_token)
            
            user_data = {
                'username': response['Username'],
                'sub': None,
                'email': None,
                'name': None
            }
            
            for attr in response['UserAttributes']:
                if attr['Name'] == 'sub':
                    user_data['sub'] = attr['Value']
                elif attr['Name'] == 'email':
                    user_data['email'] = attr['Value']
                elif attr['Name'] == 'name':
                    user_data['name'] = attr['Value']
            
            return user_data
        except ClientError as e:
            raise ValueError(f"Invalid token: {e.response['Error']['Message']}")
    
    def refresh_token(self, refresh_token: str) -> Dict:
        """Refresh access token"""
        if self.mock_mode:
            return self._mock_refresh_token(refresh_token)
        
        try:
            response = self.client.initiate_auth(
                ClientId=self.client_id,
                AuthFlow='REFRESH_TOKEN_AUTH',
                AuthParameters={
                    'REFRESH_TOKEN': refresh_token
                }
            )
            
            auth_result = response['AuthenticationResult']
            return {
                'access_token': auth_result['AccessToken'],
                'token_type': 'Bearer',
                'expires_in': auth_result['ExpiresIn']
            }
        except ClientError as e:
            raise ValueError(f"Token refresh failed: {e.response['Error']['Message']}")
    
    def confirm_signup(self, email: str, code: str):
        """Confirm user signup with verification code"""
        if self.mock_mode:
            logger.info(f"🔧 MOCK: Confirming signup for {email}")
            return
        
        try:
            self.client.confirm_sign_up(
                ClientId=self.client_id,
                Username=email,
                ConfirmationCode=code
            )
        except ClientError as e:
            raise ValueError(f"Confirmation failed: {e.response['Error']['Message']}")
    
    def admin_delete_user(self, email: str):
        """Admin: Delete a user (for cleanup)"""
        if self.mock_mode:
            logger.info(f"🔧 MOCK: Deleting user {email}")
            return
        
        try:
            self.client.admin_delete_user(
                UserPoolId=self.user_pool_id,
                Username=email
            )
        except ClientError as e:
            raise ValueError(f"User deletion failed: {e.response['Error']['Message']}")