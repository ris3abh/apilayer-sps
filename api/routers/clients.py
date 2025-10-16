# api/routers/clients.py
"""
Client Management Endpoints

Provides CRUD operations for managing clients (companies/organizations).
Each user can only access their own clients.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID
import logging

from api.dependencies import get_db, get_current_user, PaginationParams
from api.models.user import User
from api.models.client import Client
from api.schemas.client import (
    ClientCreate,
    ClientUpdate,
    ClientResponse,
    ClientListResponse
)

logger = logging.getLogger(__name__)
router = APIRouter()


# =============================================================================
# CREATE CLIENT
# =============================================================================

@router.post("", response_model=ClientResponse, status_code=status.HTTP_201_CREATED)
async def create_client(
    client_data: ClientCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Create a new client.
    
    The client will be owned by the currently authenticated user.
    
    Args:
        client_data: Client information
        
    Returns:
        Created client details
    """
    logger.info(f"Creating client '{client_data.client_name}' for user {current_user.user_id}")
    
    # Create new client
    new_client = Client(
        owner_id=current_user.user_id,
        client_name=client_data.client_name,
        industry=client_data.industry,
        target_audience=client_data.target_audience,
        brand_guidelines=client_data.brand_guidelines,
        ai_language_code=client_data.ai_language_code
    )
    
    db.add(new_client)
    db.commit()
    db.refresh(new_client)
    
    logger.info(f"✅ Client created: {new_client.client_id}")
    return new_client


# =============================================================================
# LIST CLIENTS
# =============================================================================

@router.get("", response_model=ClientListResponse)
async def list_clients(
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List all clients owned by the current user.
    
    Supports pagination via query parameters:
    - page: Page number (default: 1)
    - page_size: Items per page (default: 20, max: 100)
    
    Returns:
        List of clients with pagination metadata
    """
    logger.info(f"Fetching clients for user {current_user.user_id}")
    
    # Query clients owned by current user
    query = db.query(Client).filter(
        Client.owner_id == current_user.user_id,
        Client.is_active == True
    )
    
    # Get total count
    total = query.count()
    
    # Apply pagination
    clients = query.order_by(Client.created_at.desc())\
                   .offset(pagination.skip)\
                   .limit(pagination.limit)\
                   .all()
    
    logger.info(f"Found {total} clients, returning page {pagination.page}")
    
    return ClientListResponse(
        clients=clients,
        total=total
    )


# =============================================================================
# GET SINGLE CLIENT
# =============================================================================

@router.get("/{client_id}", response_model=ClientResponse)
async def get_client(
    client_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get a specific client by ID.
    
    Only returns the client if it's owned by the current user.
    
    Args:
        client_id: UUID of the client
        
    Returns:
        Client details
        
    Raises:
        404: Client not found or not owned by user
    """
    logger.info(f"Fetching client {client_id} for user {current_user.user_id}")
    
    client = db.query(Client).filter(
        Client.client_id == client_id,
        Client.owner_id == current_user.user_id
    ).first()
    
    if not client:
        logger.warning(f"Client {client_id} not found for user {current_user.user_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found"
        )
    
    return client


# =============================================================================
# UPDATE CLIENT
# =============================================================================

@router.patch("/{client_id}", response_model=ClientResponse)
async def update_client(
    client_id: UUID,
    client_data: ClientUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Update a client's information.
    
    Only the owner can update their clients.
    Only provided fields will be updated (partial update).
    
    Args:
        client_id: UUID of the client
        client_data: Fields to update
        
    Returns:
        Updated client details
        
    Raises:
        404: Client not found or not owned by user
    """
    logger.info(f"Updating client {client_id} for user {current_user.user_id}")
    
    # Get client
    client = db.query(Client).filter(
        Client.client_id == client_id,
        Client.owner_id == current_user.user_id
    ).first()
    
    if not client:
        logger.warning(f"Client {client_id} not found for user {current_user.user_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found"
        )
    
    # Update only provided fields
    update_data = client_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(client, field, value)
    
    db.commit()
    db.refresh(client)
    
    logger.info(f"✅ Client {client_id} updated")
    return client


# =============================================================================
# DELETE CLIENT
# =============================================================================

@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_client(
    client_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Delete a client (soft delete).
    
    Sets is_active to False instead of actually deleting.
    Only the owner can delete their clients.
    
    Args:
        client_id: UUID of the client
        
    Returns:
        204 No Content on success
        
    Raises:
        404: Client not found or not owned by user
    """
    logger.info(f"Deleting client {client_id} for user {current_user.user_id}")
    
    # Get client
    client = db.query(Client).filter(
        Client.client_id == client_id,
        Client.owner_id == current_user.user_id
    ).first()
    
    if not client:
        logger.warning(f"Client {client_id} not found for user {current_user.user_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found"
        )
    
    # Soft delete
    client.is_active = False
    db.commit()
    
    logger.info(f"✅ Client {client_id} deleted (soft delete)")
    return None
