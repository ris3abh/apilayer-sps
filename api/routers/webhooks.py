# api/routers/webhooks.py
"""
Webhook Endpoints - Receive notifications from CrewAI

These endpoints are called by CrewAI when:
1. A crew reaches a HITL checkpoint requiring human approval
2. Events occur during crew execution (task started, LLM calls, etc.)

IMPORTANT: These endpoints are called by CrewAI, not by the frontend.
Authentication uses webhook token, not user JWT.

References:
- HITL Workflows: https://docs.crewai.com/concepts/hitl-workflows
- Webhook Streaming: https://docs.crewai.com/concepts/webhook-streaming
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Dict, Any
import logging
from datetime import datetime

from api.dependencies import get_db, verify_webhook_token
from api.schemas.webhook import HITLWebhookPayload, WebhookEventsPayload, WebhookEvent
from api.models.execution import CrewExecution, ExecutionStatus
from api.models.checkpoint import HITLCheckpoint, CheckpointStatus, CheckpointType
from api.models.activity import AgentActivity, ActivityType
from api.services.sse import get_sse_manager, SSEConnectionManager

logger = logging.getLogger(__name__)
router = APIRouter()


# =============================================================================
# HITL CHECKPOINT WEBHOOK
# =============================================================================

@router.post("/hitl", status_code=status.HTTP_200_OK)
async def receive_hitl_checkpoint(
    payload: HITLWebhookPayload,
    db: Session = Depends(get_db),
    _auth: bool = Depends(verify_webhook_token),
    sse_manager: SSEConnectionManager = Depends(get_sse_manager)
):
    """
    Receive HITL checkpoint notification from CrewAI.
    
    This endpoint is called by CrewAI when a crew execution reaches a task
    with human_input=True. The crew PAUSES until we call /resume.
    
    Flow:
    1. CrewAI reaches HITL checkpoint
    2. CrewAI sends this webhook with task output
    3. Crew enters "Pending Human Input" state
    4. We store checkpoint in database
    5. Frontend displays checkpoint to user
    6. User approves/rejects via /checkpoints/{id}/approve
    7. We call CrewAI /resume to continue execution
    
    Reference: https://docs.crewai.com/concepts/hitl-workflows#step-3-receive-webhook-notification
    
    Args:
        payload: HITL webhook payload from CrewAI
        db: Database session
        _auth: Webhook authentication (validated by dependency)
    
    Returns:
        Success confirmation
    """
    logger.info(f"📥 HITL webhook received for execution: {payload.execution_id}")
    logger.info(f"   Task: {payload.task_id}")
    logger.debug(f"   Content length: {len(payload.task_output)} chars")
    
    try:
        # Find our execution record by crewai_execution_id
        execution = db.query(CrewExecution).filter(
            CrewExecution.crewai_execution_id == payload.execution_id
        ).first()
        
        if not execution:
            logger.error(f"❌ Execution not found: {payload.execution_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Execution not found: {payload.execution_id}"
            )
        
        logger.info(f"✅ Found execution: {execution.execution_id}")
        
        # Check for duplicate checkpoint (idempotency)
        existing_checkpoint = db.query(HITLCheckpoint).filter(
            HITLCheckpoint.execution_id == execution.execution_id,
            HITLCheckpoint.task_id == payload.task_id,
            HITLCheckpoint.status == CheckpointStatus.PENDING
        ).first()
        
        if existing_checkpoint:
            logger.warning(f"⚠️  Duplicate checkpoint detected, returning existing")
            return {
                "status": "received",
                "checkpoint_id": str(existing_checkpoint.checkpoint_id),
                "message": "Checkpoint already exists (idempotency)"
            }
        
        # Infer checkpoint type from task_id
        checkpoint_type = _infer_checkpoint_type(payload.task_id)
        
        # Create HITL checkpoint record
        checkpoint = HITLCheckpoint(
            execution_id=execution.execution_id,
            checkpoint_type=checkpoint_type,
            task_id=payload.task_id,
            content=payload.task_output,
            status=CheckpointStatus.PENDING,
            checkpoint_metadata={
                "agent_name": payload.agent_name,
                "received_at": datetime.utcnow().isoformat()
            }
        )
        
        db.add(checkpoint)
        
        # Create agent activity message for chat history
        activity = AgentActivity(
            execution_id=execution.execution_id,
            agent_name=payload.agent_name or "Agent",
            activity_type=ActivityType.MESSAGE,
            message=f"Checkpoint reached: {checkpoint_type.value}\n\n{payload.task_output}",
            activity_metadata={
                "checkpoint_id": str(checkpoint.checkpoint_id),
                "checkpoint_type": checkpoint_type.value,
                "task_id": payload.task_id,
                "requires_approval": True
            }
        )
        
        db.add(activity)
        
        # Update execution status
        execution.status = ExecutionStatus.AWAITING_APPROVAL
        
        # Commit all changes
        db.commit()
        db.refresh(checkpoint)
        
        logger.info(f"✅ Checkpoint created: {checkpoint.checkpoint_id}")
        logger.info(f"   Type: {checkpoint_type.value}")
        logger.info(f"   Status: {execution.status.value}")
        
        # Broadcast checkpoint to SSE clients
        await sse_manager.broadcast(
            execution_id=execution.execution_id,
            event_type="checkpoint",
            data={
                "checkpoint_id": str(checkpoint.checkpoint_id),
                "checkpoint_type": checkpoint_type.value,
                "task_id": payload.task_id,
                "requires_approval": True,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
        
        return {
            "status": "received",
            "checkpoint_id": str(checkpoint.checkpoint_id),
            "message": "Checkpoint created successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error processing HITL webhook: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process HITL webhook: {str(e)}"
        )


# =============================================================================
# EVENT STREAMING WEBHOOK
# =============================================================================

@router.post("/stream", status_code=status.HTTP_200_OK)
async def receive_event_stream(
    payload: WebhookEventsPayload,
    db: Session = Depends(get_db),
    _auth: bool = Depends(verify_webhook_token),
    sse_manager: SSEConnectionManager = Depends(get_sse_manager)
):
    """
    Receive event stream webhook from CrewAI.
    
    This endpoint receives all crew execution events for real-time monitoring
    and audit trail. Events include task started/completed, LLM calls, tool usage, etc.
    
    Citation from docs:
    "As requests are sent over HTTP, the order of events can't be guaranteed. 
    If you need ordering, use the timestamp field."
    
    Source: https://docs.crewai.com/concepts/webhook-streaming#webhook-format
    
    Args:
        payload: Event stream payload containing array of events
        db: Database session
        _auth: Webhook authentication (validated by dependency)
    
    Returns:
        Processing summary with event counts
    """
    logger.info(f"📥 Event stream webhook received with {len(payload.events)} events")
    
    processed_count = 0
    skipped_count = 0
    error_count = 0
    
    try:
        # Sort events by timestamp to maintain chronological order
        # Citation: "If you need ordering, use the timestamp field"
        sorted_events = sorted(payload.events, key=lambda e: e.timestamp)
        
        for event in sorted_events:
            try:
                # Check idempotency - have we seen this event before?
                existing_activity = db.query(AgentActivity).filter(
                    AgentActivity.activity_metadata['event_id'].astext == event.id
                ).first()
                
                if existing_activity:
                    logger.debug(f"⏭️  Skipping duplicate event: {event.id}")
                    skipped_count += 1
                    continue
                
                # Find execution
                execution = db.query(CrewExecution).filter(
                    CrewExecution.crewai_execution_id == event.execution_id
                ).first()
                
                if not execution:
                    logger.warning(f"⚠️  Execution not found for event: {event.execution_id}")
                    skipped_count += 1
                    continue
                
                # Transform event into human-readable message and activity type
                message, activity_type = _transform_event_to_message(event)
                
                # Create activity record
                activity = AgentActivity(
                    execution_id=execution.execution_id,
                    agent_name=_extract_agent_name(event),
                    activity_type=activity_type,
                    message=message,
                    timestamp=event.timestamp,
                    activity_metadata={
                        "event_id": event.id,
                        "event_type": event.type,
                        "event_data": event.data
                    }
                )
                
                db.add(activity)
                processed_count += 1
                
                # Broadcast message to SSE clients
                await sse_manager.broadcast(
                    execution_id=execution.execution_id,
                    event_type="message",
                    data={
                        "message_id": str(activity.activity_id),
                        "sender_type": "agent",
                        "sender_name": activity.agent_name,
                        "content": message,
                        "activity_type": activity_type.value,
                        "timestamp": event.timestamp.isoformat()
                    }
                )
                
            except Exception as e:
                logger.error(f"❌ Error processing event {event.id}: {str(e)}")
                error_count += 1
                continue
        
        # Commit all processed events
        db.commit()
        
        logger.info(f"✅ Event stream processed:")
        logger.info(f"   Processed: {processed_count}")
        logger.info(f"   Skipped (duplicates): {skipped_count}")
        logger.info(f"   Errors: {error_count}")
        
        return {
            "status": "received",
            "events_processed": processed_count,
            "events_skipped": skipped_count,
            "events_error": error_count,
            "total_events": len(payload.events)
        }
        
    except Exception as e:
        logger.error(f"❌ Error processing event stream: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process event stream: {str(e)}"
        )


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _infer_checkpoint_type(task_id: str) -> CheckpointType:
    """
    Infer checkpoint type from task ID.
    
    Maps task identifiers to checkpoint types based on naming conventions.
    
    Args:
        task_id: Task identifier from CrewAI
    
    Returns:
        Inferred checkpoint type
    """
    task_lower = task_id.lower()
    
    if "brand" in task_lower or "voice" in task_lower:
        return CheckpointType.BRAND_VOICE
    elif "style" in task_lower or "compliance" in task_lower:
        return CheckpointType.STYLE_COMPLIANCE
    elif "qa" in task_lower or "final" in task_lower or "review" in task_lower:
        return CheckpointType.FINAL_QA
    else:
        # Default to final QA if can't determine
        return CheckpointType.FINAL_QA


def _transform_event_to_message(event: WebhookEvent) -> tuple[str, ActivityType]:
    """
    Transform CrewAI event into human-readable message.
    
    Converts technical event types into user-friendly chat messages.
    
    Args:
        event: Webhook event from CrewAI
    
    Returns:
        Tuple of (message_text, activity_type)
    """
    event_type = event.type
    data = event.data
    
    # Task events
    if event_type == "task_started":
        task_name = data.get("task_name", data.get("task_id", "unknown"))
        return f"Started task: {task_name}", ActivityType.TASK_START
    
    elif event_type == "task_completed":
        task_name = data.get("task_name", data.get("task_id", "unknown"))
        return f"Completed task: {task_name}", ActivityType.TASK_COMPLETE
    
    elif event_type == "task_failed":
        task_name = data.get("task_name", data.get("task_id", "unknown"))
        error = data.get("error", "Unknown error")
        return f"Task failed: {task_name} - {error}", ActivityType.ERROR
    
    # Agent events
    elif event_type == "agent_execution_started":
        agent_name = data.get("agent_name", "Agent")
        return f"{agent_name} started working", ActivityType.AGENT_THINKING
    
    elif event_type == "agent_execution_completed":
        agent_name = data.get("agent_name", "Agent")
        return f"{agent_name} finished", ActivityType.AGENT_THINKING
    
    # LLM events
    elif event_type == "llm_call_started":
        model = data.get("model", "AI model")
        return f"Calling {model}", ActivityType.LLM_CALL
    
    elif event_type == "llm_call_completed":
        model = data.get("model", "AI model")
        return f"{model} responded", ActivityType.LLM_CALL
    
    # Tool events
    elif event_type == "tool_usage_started":
        tool_name = data.get("tool_name", "tool")
        return f"Using tool: {tool_name}", ActivityType.TOOL_USAGE
    
    elif event_type == "tool_usage_finished":
        tool_name = data.get("tool_name", "tool")
        return f"Finished using: {tool_name}", ActivityType.TOOL_USAGE
    
    # Crew events
    elif event_type == "crew_kickoff_started":
        return "Crew execution started", ActivityType.CREW_KICKOFF
    
    elif event_type == "crew_kickoff_completed":
        return "Crew execution completed", ActivityType.MESSAGE
    
    elif event_type == "crew_kickoff_failed":
        error = data.get("error", "Unknown error")
        return f"Crew execution failed: {error}", ActivityType.ERROR
    
    # Default for unknown event types
    else:
        return f"Event: {event_type}", ActivityType.MESSAGE


def _extract_agent_name(event: WebhookEvent) -> str:
    """
    Extract agent name from event data.
    
    Args:
        event: Webhook event from CrewAI
    
    Returns:
        Agent name or default
    """
    data = event.data
    
    # Try various fields where agent name might be
    agent_name = (
        data.get("agent_name") or
        data.get("agent") or
        data.get("actor") or
        "System"
    )
    
    return agent_name