# api/main.py
"""
Spinscribe API - Main Application

Multi-agent AI content creation platform with Human-in-the-Loop (HITL).
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import SQLAlchemyError

from api.config import settings
from api.database import engine, Base

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# =============================================================================
# APPLICATION LIFESPAN
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    
    Handles startup and shutdown events:
    - Startup: Initialize database, connections, etc.
    - Shutdown: Close connections, cleanup
    """
    # Startup
    logger.info("=" * 80)
    logger.info("🚀 SPINSCRIBE API STARTING UP")
    logger.info("=" * 80)
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"Debug Mode: {settings.DEBUG}")
    logger.info(f"API Base URL: {settings.API_BASE_URL}")
    logger.info(f"Database: {settings.DATABASE_URL.split('@')[1] if '@' in settings.DATABASE_URL else 'Not configured'}")
    logger.info(f"Redis: {settings.REDIS_URL}")
    logger.info(f"CrewAI: {settings.CREWAI_API_URL}")
    logger.info(f"S3 Buckets: {settings.DOCUMENTS_BUCKET}, {settings.OUTPUTS_BUCKET}")
    
    # Create database tables (if not exist)
    try:
        logger.info("Creating database tables...")
        Base.metadata.create_all(bind=engine)
        logger.info("✅ Database tables created/verified")
    except Exception as e:
        logger.error(f"❌ Database initialization error: {e}")
        raise
    
    # Validate critical configuration
    if not settings.OPENAI_API_KEY:
        logger.warning("⚠️  OPENAI_API_KEY not set - LLM features will not work")
    
    if not settings.CREWAI_BEARER_TOKEN:
        logger.warning("⚠️  CREWAI_BEARER_TOKEN not set - CrewAI integration will not work")
    
    logger.info("✅ Spinscribe API ready to accept requests")
    logger.info("=" * 80)
    
    yield
    
    # Shutdown
    logger.info("=" * 80)
    logger.info("🛑 SPINSCRIBE API SHUTTING DOWN")
    logger.info("=" * 80)
    logger.info("Closing database connections...")
    engine.dispose()
    logger.info("✅ Shutdown complete")
    logger.info("=" * 80)


# =============================================================================
# FASTAPI APPLICATION
# =============================================================================

app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "Multi-agent AI content creation platform with Human-in-the-Loop. "
        "Create high-quality, brand-aligned content using CrewAI agents."
    ),
    version="1.0.0",
    docs_url="/docs" if settings.DEBUG else None,  # Disable in production
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan,
    # Enable OpenAPI tags for better documentation
    openapi_tags=[
        {"name": "Health", "description": "Health check and status endpoints"},
        {"name": "Auth", "description": "Authentication and user management"},
        {"name": "Clients", "description": "Client management"},
        {"name": "Projects", "description": "Project management"},
        {"name": "Documents", "description": "Document upload and management"},
        {"name": "Executions", "description": "Crew execution and monitoring"},
        {"name": "Checkpoints", "description": "HITL checkpoint management"},
        {"name": "Webhooks", "description": "Webhook receivers for CrewAI"},
    ]
)


# =============================================================================
# MIDDLEWARE
# =============================================================================

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)


# Request Logging Middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all incoming requests"""
    logger.info(f"{request.method} {request.url.path}")
    response = await call_next(request)
    logger.info(f"{request.method} {request.url.path} - {response.status_code}")
    return response


# =============================================================================
# EXCEPTION HANDLERS
# =============================================================================

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors"""
    logger.error(f"Validation error on {request.url.path}: {exc.errors()}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": exc.errors(),
            "body": exc.body if hasattr(exc, 'body') else None
        }
    )


@app.exception_handler(SQLAlchemyError)
async def database_exception_handler(request: Request, exc: SQLAlchemyError):
    """Handle database errors"""
    logger.error(f"Database error on {request.url.path}: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "Database error occurred",
            "error": str(exc) if settings.DEBUG else "Internal server error"
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle all other exceptions"""
    logger.error(f"Unhandled error on {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "Internal server error",
            "error": str(exc) if settings.DEBUG else None
        }
    )


# =============================================================================
# ROOT ENDPOINT
# =============================================================================

@app.get("/", tags=["Health"])
async def root():
    """
    Root endpoint with API information.
    """
    return {
        "name": settings.APP_NAME,
        "version": "1.0.0",
        "status": "operational",
        "environment": settings.ENVIRONMENT,
        "docs": f"{settings.API_BASE_URL}/docs" if settings.DEBUG else None,
        "health": f"{settings.API_BASE_URL}/health"
    }


# =============================================================================
# IMPORT AND REGISTER ROUTERS
# =============================================================================

# Import routers (we'll create these next)
from api.routers import health, auth, clients, projects, webhooks, checkpoints, executions, documents

# Register routers
app.include_router(health.router, prefix="/health", tags=["Health"])
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Auth"])
app.include_router(clients.router, prefix="/api/v1/clients", tags=["Clients"])
app.include_router(projects.router, prefix="/api/v1/projects", tags=["Projects"])
app.include_router(webhooks.router, prefix="/api/v1/webhook", tags=["Webhooks"])
app.include_router(checkpoints.router, prefix="/api/v1/checkpoints", tags=["Checkpoints"])
app.include_router(executions.router, prefix="/api/v1/executions", tags=["Executions"])
app.include_router(documents.router, prefix="/api/v1/documents", tags=["Documents"])


# =============================================================================
# STARTUP MESSAGE
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    
    logger.info("=" * 80)
    logger.info("Starting Spinscribe API in development mode")
    logger.info(f"Visit: http://localhost:8000/docs for API documentation")
    logger.info("=" * 80)
    
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower()
    )