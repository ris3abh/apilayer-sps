# api/routers/projects.py
"""
Project Management Endpoints

Provides CRUD operations for managing content creation projects.
Each project belongs to a client and is created by a user.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
import logging
from datetime import datetime

from api.dependencies import get_db, get_current_user, PaginationParams
from api.models.user import User
from api.models.client import Client
from api.models.project import Project, ProjectStatus
from api.schemas.project import (
    ProjectCreate,
    ProjectUpdate,
    ProjectResponse,
    ProjectListResponse
)

logger = logging.getLogger(__name__)
router = APIRouter()


# =============================================================================
# CREATE PROJECT
# =============================================================================

@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    project_data: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Create a new project.
    
    The project will be linked to a client owned by the current user.
    
    Args:
        project_data: Project information
        
    Returns:
        Created project details
        
    Raises:
        404: Client not found or not owned by user
    """
    logger.info(f"Creating project '{project_data.project_name}' for user {current_user.user_id}")
    
    # Verify client exists and is owned by user
    client = db.query(Client).filter(
        Client.client_id == project_data.client_id,
        Client.owner_id == current_user.user_id,
        Client.is_active == True
    ).first()
    
    if not client:
        logger.warning(f"Client {project_data.client_id} not found for user {current_user.user_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found"
        )
    
    # Create new project
    new_project = Project(
        client_id=project_data.client_id,
        project_name=project_data.project_name,
        topic=project_data.topic,
        content_type=project_data.content_type,
        audience=project_data.audience,
        ai_language_code=project_data.ai_language_code,
        status=ProjectStatus.DRAFT,
        created_by=current_user.user_id
    )
    
    db.add(new_project)
    db.commit()
    db.refresh(new_project)
    
    logger.info(f"✅ Project created: {new_project.project_id}")
    return new_project


# =============================================================================
# LIST ALL PROJECTS
# =============================================================================

@router.get("", response_model=ProjectListResponse)
async def list_projects(
    status: Optional[ProjectStatus] = Query(None, description="Filter by project status"),
    content_type: Optional[str] = Query(None, description="Filter by content type"),
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List all projects created by the current user.
    
    Supports filtering and pagination:
    - status: Filter by project status (draft, in_progress, etc.)
    - content_type: Filter by content type (blog, landing_page, local_article)
    - page: Page number (default: 1)
    - page_size: Items per page (default: 20, max: 100)
    
    Returns:
        List of projects with pagination metadata
    """
    logger.info(f"Fetching projects for user {current_user.user_id}")
    
    # Build query - only show projects from user's clients
    query = db.query(Project).join(Client).filter(
        Client.owner_id == current_user.user_id,
        Client.is_active == True
    )
    
    # Apply filters
    if status:
        query = query.filter(Project.status == status)
    if content_type:
        query = query.filter(Project.content_type == content_type)
    
    # Get total count
    total = query.count()
    
    # Apply pagination
    projects = query.order_by(Project.created_at.desc())\
                    .offset(pagination.skip)\
                    .limit(pagination.limit)\
                    .all()
    
    logger.info(f"Found {total} projects, returning page {pagination.page}")
    
    return ProjectListResponse(
        projects=projects,
        total=total
    )


# =============================================================================
# LIST PROJECTS BY CLIENT
# =============================================================================

@router.get("/by-client/{client_id}", response_model=ProjectListResponse)
async def list_projects_by_client(
    client_id: UUID,
    status: Optional[ProjectStatus] = Query(None, description="Filter by project status"),
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List all projects for a specific client.
    
    Only returns projects if the client is owned by the current user.
    
    Args:
        client_id: UUID of the client
        status: Optional status filter
        
    Returns:
        List of projects for the client
        
    Raises:
        404: Client not found or not owned by user
    """
    logger.info(f"Fetching projects for client {client_id}")
    
    # Verify client exists and is owned by user
    client = db.query(Client).filter(
        Client.client_id == client_id,
        Client.owner_id == current_user.user_id,
        Client.is_active == True
    ).first()
    
    if not client:
        logger.warning(f"Client {client_id} not found for user {current_user.user_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found"
        )
    
    # Query projects for this client
    query = db.query(Project).filter(Project.client_id == client_id)
    
    # Apply status filter
    if status:
        query = query.filter(Project.status == status)
    
    # Get total count
    total = query.count()
    
    # Apply pagination
    projects = query.order_by(Project.created_at.desc())\
                    .offset(pagination.skip)\
                    .limit(pagination.limit)\
                    .all()
    
    logger.info(f"Found {total} projects for client {client_id}")
    
    return ProjectListResponse(
        projects=projects,
        total=total
    )


# =============================================================================
# GET SINGLE PROJECT
# =============================================================================

@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get a specific project by ID.
    
    Only returns the project if its client is owned by the current user.
    
    Args:
        project_id: UUID of the project
        
    Returns:
        Project details
        
    Raises:
        404: Project not found or not accessible by user
    """
    logger.info(f"Fetching project {project_id} for user {current_user.user_id}")
    
    project = db.query(Project).join(Client).filter(
        Project.project_id == project_id,
        Client.owner_id == current_user.user_id
    ).first()
    
    if not project:
        logger.warning(f"Project {project_id} not found for user {current_user.user_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    return project


# =============================================================================
# UPDATE PROJECT
# =============================================================================

@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: UUID,
    project_data: ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Update a project's information.
    
    Only the owner (via client ownership) can update projects.
    Only provided fields will be updated (partial update).
    
    When status changes to 'completed', sets completed_at timestamp.
    
    Args:
        project_id: UUID of the project
        project_data: Fields to update
        
    Returns:
        Updated project details
        
    Raises:
        404: Project not found or not accessible by user
    """
    logger.info(f"Updating project {project_id} for user {current_user.user_id}")
    
    # Get project
    project = db.query(Project).join(Client).filter(
        Project.project_id == project_id,
        Client.owner_id == current_user.user_id
    ).first()
    
    if not project:
        logger.warning(f"Project {project_id} not found for user {current_user.user_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    # Update only provided fields
    update_data = project_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(project, field, value)
    
    # If status changed to completed, set completed_at
    if 'status' in update_data and update_data['status'] == ProjectStatus.COMPLETED:
        if not project.completed_at:
            project.completed_at = datetime.utcnow()
    
    db.commit()
    db.refresh(project)
    
    logger.info(f"✅ Project {project_id} updated")
    return project


# =============================================================================
# DELETE PROJECT
# =============================================================================

@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Delete a project.
    
    Only the owner (via client ownership) can delete projects.
    This is a hard delete - the project will be permanently removed.
    
    Args:
        project_id: UUID of the project
        
    Returns:
        204 No Content on success
        
    Raises:
        404: Project not found or not accessible by user
    """
    logger.info(f"Deleting project {project_id} for user {current_user.user_id}")
    
    # Get project
    project = db.query(Project).join(Client).filter(
        Project.project_id == project_id,
        Client.owner_id == current_user.user_id
    ).first()
    
    if not project:
        logger.warning(f"Project {project_id} not found for user {current_user.user_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    # Hard delete
    db.delete(project)
    db.commit()
    
    logger.info(f"✅ Project {project_id} deleted")
    return None