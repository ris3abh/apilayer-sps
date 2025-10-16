# api/config.py
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # Environment
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"
    USE_MOCK_AUTH: bool = True
    APP_NAME: str = "Spinscribe API"  # Add this
    APP_VERSION: str = "1.0.0"  # Add this
    
    # Database
    DATABASE_URL: str
    
    # AWS
    AWS_REGION: str = "us-east-1"
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    
    # Cognito
    COGNITO_USER_POOL_ID: Optional[str] = None
    COGNITO_CLIENT_ID: Optional[str] = None
    
    # S3
    DOCUMENTS_BUCKET: str = "local-documents"
    OUTPUTS_BUCKET: str = "local-outputs"
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379"

    #OpenAI
    OPENAI_API_KEY: str = ""
    
    # CrewAI
    CREWAI_API_URL: str
    CREWAI_BEARER_TOKEN: str
    CREWAI_USER_BEARER_TOKEN: str
    
    # API
    API_BASE_URL: str = "http://localhost:8000"
    WEBHOOK_SECRET_TOKEN: str = "dev-secret"
    
    # JWT
    JWT_SECRET: str = "dev-secret-key"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_MINUTES: int = 60
    
    # CORS - as string, will be parsed to list
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"
    
    @property
    def cors_origins_list(self) -> list:
        return [x.strip() for x in self.CORS_ORIGINS.split(',')]
    
    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()