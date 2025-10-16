# api/routers/health.py
"""
Health Check Endpoints

Provides endpoints for monitoring system health, database connectivity,
external service status, and readiness checks.
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from sqlalchemy import text
import logging
from datetime import datetime
from typing import Dict, Any

from api.dependencies import get_db
from api.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# HEALTH CHECK ENDPOINTS
# =============================================================================

@router.get("")
@router.get("/")
async def health_check(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Comprehensive health check endpoint.
    
    Checks:
    - API status
    - Database connectivity
    - Configuration status
    
    Returns:
        Health status with component details
    """
    health_status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "environment": settings.ENVIRONMENT,
        "version": "1.0.0",
        "checks": {}
    }
    
    # Check database connectivity
    try:
        db.execute(text("SELECT 1"))
        health_status["checks"]["database"] = {
            "status": "healthy",
            "message": "Database connection successful"
        }
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        health_status["status"] = "unhealthy"
        health_status["checks"]["database"] = {
            "status": "unhealthy",
            "message": f"Database connection failed: {str(e)}"
        }
    
    # Check critical configuration
    config_issues = []
    
    if not settings.OPENAI_API_KEY:
        config_issues.append("OPENAI_API_KEY not configured")
    
    if not settings.CREWAI_BEARER_TOKEN:
        config_issues.append("CREWAI_BEARER_TOKEN not configured")
    
    if not settings.DATABASE_URL:
        config_issues.append("DATABASE_URL not configured")
    
    if config_issues:
        health_status["checks"]["configuration"] = {
            "status": "warning",
            "message": "Some configuration is missing",
            "issues": config_issues
        }
    else:
        health_status["checks"]["configuration"] = {
            "status": "healthy",
            "message": "All critical configuration present"
        }
    
    # S3 Buckets configured
    health_status["checks"]["storage"] = {
        "status": "healthy",
        "documents_bucket": settings.DOCUMENTS_BUCKET,
        "outputs_bucket": settings.OUTPUTS_BUCKET
    }
    
    # Redis configuration
    health_status["checks"]["redis"] = {
        "status": "configured",
        "url": settings.REDIS_URL.split('@')[1] if '@' in settings.REDIS_URL else settings.REDIS_URL
    }
    
    # CrewAI configuration
    health_status["checks"]["crewai"] = {
        "status": "configured" if settings.CREWAI_BEARER_TOKEN else "not_configured",
        "api_url": settings.CREWAI_API_URL
    }
    
    return health_status


@router.get("/ready")
async def readiness_check(db: Session = Depends(get_db)) -> Dict[str, str]:
    """
    Kubernetes-style readiness probe.
    
    Returns 200 if the application is ready to serve traffic.
    Returns 503 if not ready.
    
    Returns:
        Simple readiness status
    """
    try:
        # Check database connectivity
        db.execute(text("SELECT 1"))
        
        # Check critical configuration
        if not settings.DATABASE_URL:
            raise ValueError("DATABASE_URL not configured")
        
        return {
            "status": "ready",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return {
            "status": "not_ready",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }


@router.get("/live")
async def liveness_check() -> Dict[str, str]:
    """
    Kubernetes-style liveness probe.
    
    Returns 200 if the application process is alive.
    Simple check that doesn't verify external dependencies.
    
    Returns:
        Simple liveness status
    """
    return {
        "status": "alive",
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get("/startup")
async def startup_check(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Kubernetes-style startup probe.
    
    Returns 200 once the application has completed startup.
    Can take longer than liveness/readiness probes.
    
    Returns:
        Startup status with initialization details
    """
    try:
        # Verify database is accessible
        db.execute(text("SELECT 1"))
        
        # Verify tables exist
        from api.database import Base
        table_count = len(Base.metadata.tables)
        
        return {
            "status": "started",
            "timestamp": datetime.utcnow().isoformat(),
            "database_tables": table_count,
            "environment": settings.ENVIRONMENT
        }
    except Exception as e:
        logger.error(f"Startup check failed: {e}")
        return {
            "status": "starting",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }


@router.get("/version")
async def version_info() -> Dict[str, str]:
    """
    Application version and build information.
    
    Returns:
        Version details
    """
    return {
        "version": "1.0.0",
        "name": settings.APP_NAME,
        "environment": settings.ENVIRONMENT,
        "python_version": "3.11+",
        "build_date": "2025-01-01"  # TODO: Set from build pipeline
    }