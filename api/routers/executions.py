# api/routers/executions.py
"""
Executions Router - Crew execution management and monitoring

Handles the complete execution lifecycle:
1. Start execution → Call CrewAI kickoff
2. Monitor status → Real-time updates via SSE
3. View messages → Chat history
4. Cancel execution → Stop running crew

This is the main integration point that connects:
- CrewAI service (kickoff/resume/cancel)
- SSE manager (real-time updates)
- Database (executions, checkpoints, activities)
- Frontend (REST API + SSE stream)
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Optional
from uuid import UUID
import asyncio
import logging
from datetime import datetime

from api.dependencies import get_db, get_current_user, get_crewai_service
from api.models.user import User
from api.models.project import Project
from api.models.client import Client
from api.models.execution import CrewExecution, ExecutionStatus
from api.models.checkpoint import HITLCheckpoint, CheckpointStatus
from api.models.activity import AgentActivity, ActivityType
from api.schemas.execution import (
    StartExecutionRequest,
    StartExecutionResponse,
    ExecutionStatusResponse,
    ExecutionStatusEnum,
    MessagesResponse,
    MessageResponse,
    CancelExecutionResponse,
    WorkflowModeEnum
)
from api.services.crewai import CrewAIService
from api.services.sse import get_sse_manager, SSEConnectionManager
from api.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


# =============================================================================
# START EXECUTION
# =============================================================================

@router.post("/start", response_model=StartExecutionResponse, status_code=status.HTTP_201_CREATED)
async def start_execution(
    request: StartExecutionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    crewai_service: CrewAIService = Depends(get_crewai_service)
):
    """
    Start a new crew execution.
    
    This endpoint:
    1. Validates the project belongs to the user
    2. Creates an execution record in the database
    3. Prepares inputs for CrewAI crew
    4. Calls CrewAI /kickoff endpoint (with webhook URLs)
    5. Returns execution details and SSE stream URL
    
    The crew will run asynchronously. Use the SSE stream or status
    endpoint to monitor progress.
    
    Args:
        request: Execution start request
        db: Database session
        current_user: Authenticated user
        crewai_service: CrewAI service instance
    
    Returns:
        Execution details with stream URL
    
    Raises:
        404: Project not found or user doesn't have access
        500: Failed to start execution
    """
    logger.info(f"🚀 Starting execution for project: {request.project_id}")
    logger.info(f"   User: {current_user.email}")
    logger.info(f"   Mode: {request.workflow_mode.value}")
    
    try:
        # Get project with ownership verification
        project = db.query(Project).join(
            Client, Project.client_id == Client.client_id
        ).filter(
            Project.project_id == request.project_id,
            Client.owner_id == current_user.user_id
        ).first()
        
        if not project:
            logger.warning(f"❌ Project {request.project_id} not found for user {current_user.user_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )
        
        logger.info(f"✅ Project found: {project.project_name}")
        
        # Create execution record
        execution = CrewExecution(
            project_id=project.project_id,
            workflow_mode=request.workflow_mode.value,
            status=ExecutionStatus.PENDING,
            created_by=current_user.user_id,
            started_at=datetime.utcnow()
        )
        
        db.add(execution)
        db.flush()  # Get execution_id without committing
        
        logger.info(f"💾 Execution record created: {execution.execution_id}")
        
        # Prepare inputs for CrewAI crew
        crew_inputs = {
            # Required crew inputs
            "topic": project.topic,
            "client_name": project.client.client_name,
            "content_type": project.content_type,
            "audience": project.audience,
            "ai_language_code": project.ai_language_code or "/TN/A3,P4/VL4/SC3/FL2",
            "workflow_mode": request.workflow_mode.value,
            
            # Additional fields for S3 access
            "client_id": str(project.client_id),
            
            # MISSING FIELDS - Add defaults for creation mode
            "content_length": "1500",
            "initial_draft": "",
            "draft_source": "none",
            "draft_length": "0",
            "draft_word_count": "0",
        }
        
        # Add workflow-specific inputs
        if request.workflow_mode == WorkflowModeEnum.REVISION:
            crew_inputs["initial_draft"] = request.initial_draft or ""
            crew_inputs["draft_source"] = "human"
            crew_inputs["draft_length"] = str(len(request.initial_draft or ""))
            crew_inputs["draft_word_count"] = str(len((request.initial_draft or "").split()))
            crew_inputs["revision_instructions"] = request.revision_instructions or ""
        elif request.workflow_mode == WorkflowModeEnum.REPURPOSE:
            crew_inputs["initial_draft"] = ""
            crew_inputs["draft_source"] = "ai_generated"
        
        
        logger.debug(f"Inputs: {crew_inputs}")
        logger.info(f"📋 Crew inputs prepared")
        logger.info(f"   Required crew inputs: {list(crew_inputs.keys())}")
        logger.debug(f"   Full inputs: {crew_inputs}")
        
        # Call CrewAI kickoff
        try:
            kickoff_result = await crewai_service.kickoff_crew(
                inputs=crew_inputs,
                execution_id=str(execution.execution_id)
            )
            
            # Update execution with CrewAI execution ID
            execution.crewai_execution_id = kickoff_result.get("kickoff_id")
            execution.status = ExecutionStatus.RUNNING
            
            # Create initial activity
            activity = AgentActivity(
                execution_id=execution.execution_id,
                agent_name="System",
                activity_type=ActivityType.CREW_KICKOFF,
                message=f"Crew execution started in {request.workflow_mode.value} mode"
            )
            db.add(activity)
            
            db.commit()
            db.refresh(execution)
            
            logger.info(f"✅ CrewAI kickoff successful!")
            logger.info(f"   CrewAI execution ID: {execution.crewai_execution_id}")
            
            # Build SSE stream URL
            stream_url = f"{settings.API_BASE_URL}/api/v1/executions/{execution.execution_id}/stream"
            
            return StartExecutionResponse(
                execution_id=execution.execution_id,
                project_id=project.project_id,
                status=ExecutionStatusEnum.RUNNING,
                crewai_execution_id=execution.crewai_execution_id,
                message="Execution started successfully. Connect to stream for real-time updates.",
                stream_url=stream_url
            )
            
        except Exception as e:
            logger.error(f"❌ CrewAI kickoff failed: {str(e)}", exc_info=True)
            logger.error(f"Exception type: {type(e).__name__}")
            logger.error(f"Full error: {repr(e)}")
            
            # Update execution status to failed
            execution.status = ExecutionStatus.FAILED
            execution.error_message = f"Failed to start crew: {str(e)}"
            db.commit()
            
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to start crew execution: {str(e)}"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error starting execution: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start execution: {str(e)}"
        )


# =============================================================================
# GET EXECUTION STATUS
# =============================================================================

@router.get("/{execution_id}/status", response_model=ExecutionStatusResponse)
async def get_execution_status(
    execution_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    sse_manager: SSEConnectionManager = Depends(get_sse_manager)
):
    """
    Get current status and progress of an execution.
    
    Returns detailed information including:
    - Current status and task
    - Progress percentage
    - Pending checkpoints
    - Error messages (if failed)
    - Active SSE connection count
    
    Args:
        execution_id: UUID of the execution
        db: Database session
        current_user: Authenticated user
        sse_manager: SSE connection manager
    
    Returns:
        Execution status and progress information
    
    Raises:
        404: Execution not found or user doesn't have access
    """
    logger.info(f"📊 Getting status for execution: {execution_id}")
    
    # Get execution with ownership verification
    execution = db.query(CrewExecution).join(
        Project, CrewExecution.project_id == Project.project_id
    ).join(
        Client, Project.client_id == Client.client_id
    ).filter(
        CrewExecution.execution_id == execution_id,
        Client.owner_id == current_user.user_id
    ).first()
    
    if not execution:
        logger.warning(f"❌ Execution {execution_id} not found for user {current_user.user_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Execution not found"
        )
    
    # Check for pending checkpoint
    pending_checkpoint = None
    if execution.status == ExecutionStatus.AWAITING_APPROVAL:
        checkpoint = db.query(HITLCheckpoint).filter(
            HITLCheckpoint.execution_id == execution.execution_id,
            HITLCheckpoint.status == CheckpointStatus.PENDING
        ).first()
        
        if checkpoint:
            pending_checkpoint = {
                "checkpoint_id": str(checkpoint.checkpoint_id),
                "checkpoint_type": checkpoint.checkpoint_type.value,
                "task_id": checkpoint.task_id,
                "created_at": checkpoint.created_at.isoformat()
            }
    
    # Get active connection count
    active_connections = sse_manager.get_connection_count(execution_id)
    
    # Map status to enum
    status_map = {
        ExecutionStatus.PENDING: ExecutionStatusEnum.PENDING,
        ExecutionStatus.RUNNING: ExecutionStatusEnum.RUNNING,
        ExecutionStatus.AWAITING_APPROVAL: ExecutionStatusEnum.AWAITING_APPROVAL,
        ExecutionStatus.COMPLETED: ExecutionStatusEnum.COMPLETED,
        ExecutionStatus.FAILED: ExecutionStatusEnum.FAILED,
        ExecutionStatus.CANCELLED: ExecutionStatusEnum.CANCELLED,
    }
    
    logger.info(f"✅ Status: {execution.status.value}, Connections: {active_connections}")
    
    return ExecutionStatusResponse(
        execution_id=execution.execution_id,
        project_id=execution.project_id,
        status=status_map[execution.status],
        workflow_mode=WorkflowModeEnum(execution.workflow_mode),
        started_at=execution.started_at,
        completed_at=execution.completed_at,
        current_task=None,  # TODO: Extract from latest activity
        progress_percentage=None,  # TODO: Calculate based on tasks
        pending_checkpoint=pending_checkpoint,
        error_message=execution.error_message,
        metrics=execution.metrics or {},
        active_connections=active_connections
    )


# =============================================================================
# GET EXECUTION MESSAGES
# =============================================================================

@router.get("/{execution_id}/messages", response_model=MessagesResponse)
async def get_execution_messages(
    execution_id: UUID,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get chat history (messages) for an execution.
    
    Returns all agent activities as chat messages in chronological order.
    Supports pagination for long conversations.
    
    Args:
        execution_id: UUID of the execution
        limit: Maximum number of messages to return (1-100)
        offset: Pagination offset
        db: Database session
        current_user: Authenticated user
    
    Returns:
        List of messages with pagination info
    
    Raises:
        404: Execution not found or user doesn't have access
    """
    logger.info(f"💬 Getting messages for execution: {execution_id}")
    
    # Verify ownership
    execution = db.query(CrewExecution).join(
        Project, CrewExecution.project_id == Project.project_id
    ).join(
        Client, Project.client_id == Client.client_id
    ).filter(
        CrewExecution.execution_id == execution_id,
        Client.owner_id == current_user.user_id
    ).first()
    
    if not execution:
        logger.warning(f"❌ Execution {execution_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Execution not found"
        )
    
    # Get total count
    total = db.query(AgentActivity).filter(
        AgentActivity.execution_id == execution_id
    ).count()
    
    # Get messages with pagination
    activities = db.query(AgentActivity).filter(
        AgentActivity.execution_id == execution_id
    ).order_by(
        AgentActivity.timestamp.asc()
    ).offset(offset).limit(limit).all()
    
    # Convert to message responses
    messages = []
    for activity in activities:
        # Determine sender type
        sender_type = "agent"
        if activity.agent_name == "System":
            sender_type = "system"
        elif activity.activity_metadata.get("is_human"):
            sender_type = "user"
        
        messages.append(MessageResponse(
            message_id=activity.activity_id,
            timestamp=activity.timestamp,
            sender_type=sender_type,
            sender_name=activity.agent_name,
            activity_type=activity.activity_type.value,
            content=activity.message,
            metadata=activity.activity_metadata or {}
        ))
    
    logger.info(f"✅ Returning {len(messages)} messages (total: {total})")
    
    return MessagesResponse(
        execution_id=execution_id,
        messages=messages,
        total=total,
        has_more=(offset + limit) < total
    )


# =============================================================================
# SSE STREAM
# =============================================================================

@router.get("/{execution_id}/stream")
async def stream_execution_events(
    execution_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    sse_manager: SSEConnectionManager = Depends(get_sse_manager)
):
    """
    Server-Sent Events (SSE) stream for real-time execution updates.
    
    Streams events as they occur:
    - New messages from agents
    - Status changes
    - Checkpoint notifications
    - Completion/failure events
    
    Connection lifecycle:
    1. Client connects to this endpoint
    2. Connection registered in SSE manager
    3. Events broadcast to all connected clients
    4. Client disconnects → cleanup
    
    Args:
        execution_id: UUID of the execution to stream
        request: FastAPI request (for disconnect detection)
        db: Database session
        current_user: Authenticated user
        sse_manager: SSE connection manager
    
    Returns:
        StreamingResponse with SSE events
    
    Raises:
        404: Execution not found or user doesn't have access
        429: Too many connections (limit: 3 per user)
    """
    logger.info(f"🔌 SSE connection request for execution: {execution_id}")
    logger.info(f"   User: {current_user.email}")
    
    # Verify ownership
    execution = db.query(CrewExecution).join(
        Project, CrewExecution.project_id == Project.project_id
    ).join(
        Client, Project.client_id == Client.client_id
    ).filter(
        CrewExecution.execution_id == execution_id,
        Client.owner_id == current_user.user_id
    ).first()
    
    if not execution:
        logger.warning(f"❌ Execution {execution_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Execution not found"
        )
    
    # Create queue for this connection
    queue: asyncio.Queue = asyncio.Queue()
    
    # Register connection
    connected = await sse_manager.connect(
        execution_id=execution_id,
        user_id=current_user.user_id,
        queue=queue
    )
    
    if not connected:
        logger.warning(f"❌ Connection limit reached for user {current_user.user_id}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Connection limit reached ({sse_manager.MAX_CONNECTIONS_PER_USER} max)"
        )
    
    async def event_generator():
        """Generate SSE events from the queue."""
        try:
            # Send initial connection event
            yield sse_manager._format_sse_message(
                "connected",
                {
                    "execution_id": str(execution_id),
                    "status": execution.status.value,
                    "message": "Connected to execution stream"
                }
            )
            
            # Send events from queue
            while True:
                # Check if client disconnected
                if await request.is_disconnected():
                    logger.info(f"🔌 Client disconnected from stream")
                    break
                
                try:
                    # Wait for event with timeout (for heartbeat)
                    event = await asyncio.wait_for(
                        queue.get(),
                        timeout=sse_manager.HEARTBEAT_INTERVAL
                    )
                    yield event
                    
                except asyncio.TimeoutError:
                    # Send heartbeat
                    await sse_manager.send_heartbeat(queue)
                    continue
        
        finally:
            # Cleanup on disconnect
            sse_manager.disconnect(queue)
            logger.info(f"✅ SSE connection cleaned up")
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )


# =============================================================================
# CANCEL EXECUTION
# =============================================================================

@router.delete("/{execution_id}", response_model=CancelExecutionResponse)
async def cancel_execution(
    execution_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    crewai_service: CrewAIService = Depends(get_crewai_service),
    sse_manager: SSEConnectionManager = Depends(get_sse_manager)
):
    """
    Cancel a running execution.
    
    Attempts to:
    1. Cancel the CrewAI execution (if running)
    2. Update execution status to CANCELLED
    3. Broadcast cancellation to connected clients
    
    Args:
        execution_id: UUID of the execution to cancel
        db: Database session
        current_user: Authenticated user
        crewai_service: CrewAI service instance
        sse_manager: SSE manager for broadcasting
    
    Returns:
        Cancellation confirmation
    
    Raises:
        404: Execution not found or user doesn't have access
        400: Execution already completed/cancelled
    """
    logger.info(f"🛑 Cancelling execution: {execution_id}")
    
    # Get execution with ownership verification
    execution = db.query(CrewExecution).join(
        Project, CrewExecution.project_id == Project.project_id
    ).join(
        Client, Project.client_id == Client.client_id
    ).filter(
        CrewExecution.execution_id == execution_id,
        Client.owner_id == current_user.user_id
    ).first()
    
    if not execution:
        logger.warning(f"❌ Execution {execution_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Execution not found"
        )
    
    # Check if already completed/cancelled
    if execution.status in [ExecutionStatus.COMPLETED, ExecutionStatus.CANCELLED, ExecutionStatus.FAILED]:
        logger.warning(f"⚠️  Execution already {execution.status.value}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel execution with status: {execution.status.value}"
        )
    
    # Try to cancel in CrewAI
    crewai_cancelled = False
    if execution.crewai_execution_id:
        try:
            crewai_cancelled = await crewai_service.cancel_execution(
                execution.crewai_execution_id
            )
            logger.info(f"CrewAI cancellation: {crewai_cancelled}")
        except Exception as e:
            logger.warning(f"⚠️  CrewAI cancellation failed: {e}")
    
    # Update execution status
    execution.status = ExecutionStatus.CANCELLED
    execution.completed_at = datetime.utcnow()
    
    # Create cancellation activity
    activity = AgentActivity(
        execution_id=execution.execution_id,
        agent_name=current_user.name,
        activity_type=ActivityType.MESSAGE,
        message=f"Execution cancelled by {current_user.name}",
        activity_metadata={"is_human": True}
    )
    db.add(activity)
    
    db.commit()
    
    # Broadcast cancellation to SSE clients
    await sse_manager.broadcast(
        execution_id=execution_id,
        event_type="cancelled",
        data={
            "execution_id": str(execution_id),
            "cancelled_by": current_user.name,
            "timestamp": datetime.utcnow().isoformat()
        }
    )
    
    logger.info(f"✅ Execution cancelled successfully")
    
    return CancelExecutionResponse(
        execution_id=execution_id,
        status=ExecutionStatusEnum.CANCELLED,
        message="Execution cancelled successfully",
        crewai_cancelled=crewai_cancelled
    )