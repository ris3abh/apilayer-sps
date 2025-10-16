# api/routers/checkpoints.py
"""
Checkpoint Management Endpoints

Handles HITL (Human-in-the-Loop) checkpoint operations:
- Listing pending checkpoints
- Viewing checkpoint details
- Approving checkpoints (resumes CrewAI execution)
- Rejecting checkpoints (requests revision)

These endpoints are used by the frontend for human review and approval.

References:
- HITL Workflows: https://docs.crewai.com/concepts/hitl-workflows
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from datetime import datetime
import logging

from api.dependencies import get_db, get_current_user, get_crewai_service
from api.models.user import User
from api.models.project import Project
from api.models.client import Client
from api.services.sse import get_sse_manager, SSEConnectionManager
from api.models.checkpoint import HITLCheckpoint, CheckpointStatus, CheckpointType
from api.models.execution import CrewExecution, ExecutionStatus
from api.models.activity import AgentActivity, ActivityType
from api.schemas.webhook import (
    CheckpointResponse,
    PendingCheckpointsResponse,
    HITLApprovalRequest,
    HITLApprovalResponse
)
from api.services.crewai import CrewAIService

logger = logging.getLogger(__name__)
router = APIRouter()


# =============================================================================
# LIST PENDING CHECKPOINTS
# =============================================================================

@router.get("/pending", response_model=PendingCheckpointsResponse)
async def list_pending_checkpoints(
    checkpoint_type: Optional[CheckpointType] = Query(None, description="Filter by checkpoint type"),
    project_id: Optional[UUID] = Query(None, description="Filter by project"),
    limit: int = Query(20, ge=1, le=100, description="Maximum results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List all pending checkpoints for the current user.
    
    Returns checkpoints from executions owned by the user (via project → client → user).
    Useful for displaying a "tasks awaiting approval" dashboard.
    
    Args:
        checkpoint_type: Optional filter by checkpoint type
        project_id: Optional filter by specific project
        limit: Maximum number of results (1-100)
        offset: Pagination offset
        db: Database session
        current_user: Authenticated user
    
    Returns:
        List of pending checkpoints with pagination info
    """
    logger.info(f"📋 Listing pending checkpoints for user: {current_user.user_id}")
    
    # Build query - only show checkpoints from user's executions
    query = db.query(HITLCheckpoint).join(
    CrewExecution, HITLCheckpoint.execution_id == CrewExecution.execution_id
        ).join(
            Project, CrewExecution.project_id == Project.project_id
        ).join(
            Client, Project.client_id == Client.client_id
        ).filter(
            HITLCheckpoint.status == CheckpointStatus.PENDING,
            Client.owner_id == current_user.user_id
        )
    
    # Apply optional filters
    if checkpoint_type:
        query = query.filter(HITLCheckpoint.checkpoint_type == checkpoint_type)
    
    if project_id:
        query = query.filter(CrewExecution.project_id == project_id)
    
    # Order by creation time (newest first)
    query = query.order_by(HITLCheckpoint.created_at.desc())
    
    # Get total count
    total = query.count()
    
    # Apply pagination
    checkpoints = query.offset(offset).limit(limit).all()
    
    logger.info(f"✅ Found {len(checkpoints)} pending checkpoints (total: {total})")
    
    return PendingCheckpointsResponse(
        checkpoints=[CheckpointResponse.from_orm(cp) for cp in checkpoints],
        total=total,
        limit=limit,
        offset=offset
    )


# =============================================================================
# GET SPECIFIC CHECKPOINT
# =============================================================================

@router.get("/{checkpoint_id}", response_model=CheckpointResponse)
async def get_checkpoint(
    checkpoint_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get detailed information about a specific checkpoint.
    
    Includes the full content that needs review and execution context.
    
    Args:
        checkpoint_id: UUID of the checkpoint
        db: Database session
        current_user: Authenticated user
    
    Returns:
        Detailed checkpoint information
    
    Raises:
        404: Checkpoint not found or user doesn't have access
    """
    logger.info(f"📄 Getting checkpoint: {checkpoint_id}")
    
    # Get checkpoint with ownership verification
    checkpoint = db.query(HITLCheckpoint).join(
        CrewExecution, HITLCheckpoint.execution_id == CrewExecution.execution_id
    ).join(
        Project, CrewExecution.project_id == Project.project_id
    ).join(
        Client, Project.client_id == Client.client_id
    ).filter(
        HITLCheckpoint.checkpoint_id == checkpoint_id,
        Client.owner_id == current_user.user_id
    ).first()
    
    if not checkpoint:
        logger.warning(f"❌ Checkpoint {checkpoint_id} not found for user {current_user.user_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Checkpoint not found"
        )
    
    logger.info(f"✅ Checkpoint found: {checkpoint.checkpoint_type.value} - {checkpoint.status.value}")
    
    return CheckpointResponse.from_orm(checkpoint)


# =============================================================================
# APPROVE CHECKPOINT
# =============================================================================

@router.post("/{checkpoint_id}/approve", response_model=HITLApprovalResponse)
async def approve_checkpoint(
    checkpoint_id: UUID,
    approval: HITLApprovalRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    crewai_service: CrewAIService = Depends(get_crewai_service),
    sse_manager: SSEConnectionManager = Depends(get_sse_manager)
):
    """
    Approve a checkpoint and resume CrewAI execution.
    
    This endpoint:
    1. Updates the checkpoint status to APPROVED
    2. Stores the human feedback
    3. Creates a chat message with the approval
    4. Calls CrewAI /resume endpoint to continue execution
    5. Updates execution status to RUNNING
    
    CRITICAL: Must re-provide webhook URLs to CrewAI resume call.
    
    Citation from docs:
    "You must provide the same webhook URLs in the resume call that you 
    used in the kickoff call. Webhook configurations are NOT automatically 
    carried over from kickoff."
    
    Source: https://docs.crewai.com/concepts/hitl-workflows#step-5-submit-human-feedback
    
    Args:
        checkpoint_id: UUID of the checkpoint to approve
        approval: Approval request with feedback
        db: Database session
        current_user: Authenticated user
        crewai_service: CrewAI service instance
    
    Returns:
        Approval confirmation with resume status
    
    Raises:
        404: Checkpoint not found
        400: Checkpoint not in pending state
        500: Failed to resume CrewAI execution
    """
    logger.info(f"✅ Approving checkpoint: {checkpoint_id}")
    logger.info(f"   User: {current_user.email}")
    logger.debug(f"   Feedback: {approval.feedback[:100]}...")
    
    try:
        # Get checkpoint with ownership verification
        checkpoint = db.query(HITLCheckpoint).join(
            CrewExecution, HITLCheckpoint.execution_id == CrewExecution.execution_id
        ).join(
            Project, CrewExecution.project_id == Project.project_id
        ).join(
            Client, Project.client_id == Client.client_id
        ).filter(
            HITLCheckpoint.checkpoint_id == checkpoint_id,
            Client.owner_id == current_user.user_id
        ).first()
        
        if not checkpoint:
            logger.warning(f"❌ Checkpoint {checkpoint_id} not found")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Checkpoint not found"
            )
        
        # Verify checkpoint is in PENDING state
        if checkpoint.status != CheckpointStatus.PENDING:
            logger.warning(f"❌ Checkpoint not pending: {checkpoint.status.value}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Checkpoint is not pending. Current status: {checkpoint.status.value}"
            )
        
        # Get execution
        execution = checkpoint.execution
        
        if not execution.crewai_execution_id:
            logger.error(f"❌ Execution has no CrewAI ID")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Execution has no CrewAI execution ID"
            )
        
        # Update checkpoint
        checkpoint.status = CheckpointStatus.APPROVED
        checkpoint.reviewer_feedback = approval.feedback
        checkpoint.reviewed_by = current_user.user_id
        checkpoint.reviewed_at = datetime.utcnow()
        
        # Create activity record for human approval
        activity = AgentActivity(
            execution_id=execution.execution_id,
            agent_name=current_user.name,
            activity_type=ActivityType.MESSAGE,
            message=f"✅ Approved: {approval.feedback}",
            activity_metadata={
                "checkpoint_id": str(checkpoint.checkpoint_id),
                "checkpoint_type": checkpoint.checkpoint_type.value,
                "is_approval": True,
                "reviewer_id": str(current_user.user_id)
            }
        )
        db.add(activity)
        
        # Commit checkpoint and activity updates before calling CrewAI
        db.commit()
        db.refresh(checkpoint)
        
        logger.info(f"💾 Checkpoint updated in database")
        logger.info(f"🔄 Calling CrewAI resume endpoint...")
        
        # Call CrewAI to resume execution
        # CRITICAL: Re-provide webhook URLs!
        try:
            resume_result = await crewai_service.resume_crew(
                crewai_execution_id=execution.crewai_execution_id,
                task_id=checkpoint.task_id,
                human_feedback=approval.feedback,
                is_approve=True  # This is an approval
            )
            
            logger.info(f"✅ CrewAI resume successful!")
            
            # Update execution status
            execution.status = ExecutionStatus.RUNNING
            db.commit()
            
            # Broadcast approval to SSE clients
            await sse_manager.broadcast(
                execution_id=execution.execution_id,
                event_type="approval",
                data={
                    "checkpoint_id": str(checkpoint.checkpoint_id),
                    "approved": True,
                    "feedback": approval.feedback,
                    "reviewer": current_user.name,
                    "timestamp": datetime.utcnow().isoformat()
                }
            )
            
            return HITLApprovalResponse(
                status="success",
                checkpoint_id=checkpoint.checkpoint_id,
                execution_id=execution.execution_id,
                message="Checkpoint approved. Crew execution resumed.",
                crew_resumed=True,
                will_retry=False
            )
            
        except Exception as e:
            logger.error(f"❌ Failed to resume CrewAI execution: {str(e)}")
            
            # Rollback checkpoint status since resume failed
            checkpoint.status = CheckpointStatus.PENDING
            checkpoint.reviewed_by = None
            checkpoint.reviewed_at = None
            db.commit()
            
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to resume crew execution: {str(e)}"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error approving checkpoint: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to approve checkpoint: {str(e)}"
        )


# =============================================================================
# REJECT CHECKPOINT
# =============================================================================

@router.post("/{checkpoint_id}/reject", response_model=HITLApprovalResponse)
async def reject_checkpoint(
    checkpoint_id: UUID,
    rejection: HITLApprovalRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    crewai_service: CrewAIService = Depends(get_crewai_service),
    sse_manager: SSEConnectionManager = Depends(get_sse_manager)
):
    """
    Reject a checkpoint and request revision.
    
    When rejected, CrewAI will retry the task with the provided feedback
    as additional context.
    
    Citation from docs:
    "If you provide negative feedback: The crew will retry the task with 
    added context from your feedback. You'll receive another webhook 
    notification for further review."
    
    Source: https://docs.crewai.com/concepts/hitl-workflows#step-6-handle-negative-feedback
    
    Args:
        checkpoint_id: UUID of the checkpoint to reject
        rejection: Rejection request with feedback explaining what needs improvement
        db: Database session
        current_user: Authenticated user
        crewai_service: CrewAI service instance
    
    Returns:
        Rejection confirmation with retry status
    
    Raises:
        404: Checkpoint not found
        400: Checkpoint not in pending state
        500: Failed to resume CrewAI execution
    """
    logger.info(f"❌ Rejecting checkpoint: {checkpoint_id}")
    logger.info(f"   User: {current_user.email}")
    logger.debug(f"   Feedback: {rejection.feedback[:100]}...")
    
    # Most logic is the same as approve, just with different status and is_approve=False
    try:
        # Get checkpoint with ownership verification
        checkpoint = db.query(HITLCheckpoint).join(
            CrewExecution, HITLCheckpoint.execution_id == CrewExecution.execution_id
        ).join(
            Project, CrewExecution.project_id == Project.project_id
        ).join(
            Client, Project.client_id == Client.client_id
        ).filter(
            HITLCheckpoint.checkpoint_id == checkpoint_id,
            Client.owner_id == current_user.user_id
        ).first()
        
        if not checkpoint:
            logger.warning(f"❌ Checkpoint {checkpoint_id} not found")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Checkpoint not found"
            )
        
        # Verify checkpoint is in PENDING state
        if checkpoint.status != CheckpointStatus.PENDING:
            logger.warning(f"❌ Checkpoint not pending: {checkpoint.status.value}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Checkpoint is not pending. Current status: {checkpoint.status.value}"
            )
        
        # Get execution
        execution = checkpoint.execution
        
        if not execution.crewai_execution_id:
            logger.error(f"❌ Execution has no CrewAI ID")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Execution has no CrewAI execution ID"
            )
        
        # Update checkpoint
        checkpoint.status = CheckpointStatus.REJECTED
        checkpoint.reviewer_feedback = rejection.feedback
        checkpoint.reviewed_by = current_user.user_id
        checkpoint.reviewed_at = datetime.utcnow()
        
        # Create activity record for human rejection
        activity = AgentActivity(
            execution_id=execution.execution_id,
            agent_name=current_user.name,
            activity_type=ActivityType.MESSAGE,
            message=f"🔄 Revision requested: {rejection.feedback}",
            activity_metadata={
                "checkpoint_id": str(checkpoint.checkpoint_id),
                "checkpoint_type": checkpoint.checkpoint_type.value,
                "is_approval": False,
                "reviewer_id": str(current_user.user_id)
            }
        )
        db.add(activity)
        
        # Commit updates
        db.commit()
        db.refresh(checkpoint)
        
        logger.info(f"💾 Checkpoint rejected in database")
        logger.info(f"🔄 Calling CrewAI resume endpoint with negative feedback...")
        
        # Call CrewAI to resume with rejection
        try:
            resume_result = await crewai_service.resume_crew(
                crewai_execution_id=execution.crewai_execution_id,
                task_id=checkpoint.task_id,
                human_feedback=rejection.feedback,
                is_approve=False  # This is a rejection
            )
            
            logger.info(f"✅ CrewAI resume successful! Agent will retry task.")
            
            # Keep execution in AWAITING_APPROVAL state
            # (will change when agent submits revised work)
            execution.status = ExecutionStatus.RUNNING
            db.commit()
            
            # Broadcast rejection to SSE clients
            await sse_manager.broadcast(
                execution_id=execution.execution_id,
                event_type="approval",
                data={
                    "checkpoint_id": str(checkpoint.checkpoint_id),
                    "approved": False,
                    "will_retry": True,
                    "feedback": rejection.feedback,
                    "reviewer": current_user.name,
                    "timestamp": datetime.utcnow().isoformat()
                }
            )
            
            return HITLApprovalResponse(
                status="success",
                checkpoint_id=checkpoint.checkpoint_id,
                execution_id=execution.execution_id,
                message="Checkpoint rejected. Agent will revise based on feedback.",
                crew_resumed=True,
                will_retry=True
            )
            
        except Exception as e:
            logger.error(f"❌ Failed to resume CrewAI execution: {str(e)}")
            
            # Rollback checkpoint status
            checkpoint.status = CheckpointStatus.PENDING
            checkpoint.reviewed_by = None
            checkpoint.reviewed_at = None
            db.commit()
            
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to resume crew execution: {str(e)}"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error rejecting checkpoint: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reject checkpoint: {str(e)}"
        )