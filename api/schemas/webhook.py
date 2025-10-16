# api/schemas/webhook.py
"""
Webhook Schemas - Pydantic models for CrewAI webhook payloads

These schemas define the structure of webhook notifications we receive from CrewAI.

References:
- HITL Workflows: https://docs.crewai.com/concepts/hitl-workflows
- Webhook Streaming: https://docs.crewai.com/concepts/webhook-streaming
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
from uuid import UUID


# =============================================================================
# HITL WEBHOOK SCHEMAS
# =============================================================================

class HITLWebhookPayload(BaseModel):
    """
    Payload received from CrewAI when crew reaches HITL checkpoint.
    
    This is sent when a task with human_input=True completes and requires
    human approval before the crew can continue.
    
    Reference: https://docs.crewai.com/concepts/hitl-workflows#step-3-receive-webhook-notification
    
    Example payload from CrewAI:
    {
        "execution_id": "abcd1234-5678-90ef-ghij-klmnopqrstuv",
        "task_id": "brand_voice_analysis",
        "task_output": "Analysis complete. Key findings: ..."
    }
    """
    execution_id: str = Field(
        ...,
        description="CrewAI execution ID (kickoff_id from /kickoff response)"
    )
    task_id: str = Field(
        ...,
        description="Task identifier from the crew definition"
    )
    task_output: str = Field(
        ...,
        description="Content or analysis output that needs human review"
    )
    
    # Optional fields that may be included
    agent_name: Optional[str] = Field(
        None,
        description="Name of the agent that generated the output"
    )
    timestamp: Optional[datetime] = Field(
        None,
        description="When the checkpoint was reached"
    )


# =============================================================================
# EVENT STREAMING WEBHOOK SCHEMAS
# =============================================================================

class WebhookEvent(BaseModel):
    """
    Individual event from CrewAI event stream.
    
    Reference: https://docs.crewai.com/concepts/webhook-streaming#webhook-format
    
    Example event:
    {
        "id": "evt-123",
        "execution_id": "crew-run-id",
        "timestamp": "2025-02-16T10:58:44.965Z",
        "type": "task_started",
        "data": {
            "task_id": "research_task",
            "task_name": "Research Industry Trends"
        }
    }
    """
    id: str = Field(
        ...,
        description="Unique event identifier (use for idempotency)"
    )
    execution_id: str = Field(
        ...,
        description="CrewAI execution ID this event belongs to"
    )
    timestamp: datetime = Field(
        ...,
        description="When the event occurred (ISO format)"
    )
    type: str = Field(
        ...,
        description="Event type (e.g., task_started, llm_call_completed)"
    )
    data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Event-specific data (structure varies by event type)"
    )


class WebhookEventsPayload(BaseModel):
    """
    Payload received from CrewAI event streaming webhook.
    
    Contains a list of events that occurred during crew execution.
    When realtime=false, events are batched together.
    
    Reference: https://docs.crewai.com/concepts/webhook-streaming#webhook-format
    
    Citation from docs:
    "As requests are sent over HTTP, the order of events can't be guaranteed. 
    If you need ordering, use the timestamp field."
    
    Example payload:
    {
        "events": [
            {
                "id": "evt-1",
                "execution_id": "crew-123",
                "timestamp": "2025-02-16T10:58:44.965Z",
                "type": "task_started",
                "data": {...}
            },
            {
                "id": "evt-2",
                "execution_id": "crew-123",
                "timestamp": "2025-02-16T10:58:45.123Z",
                "type": "llm_call_started",
                "data": {...}
            }
        ]
    }
    """
    events: List[WebhookEvent] = Field(
        ...,
        description="Array of events (can contain multiple events when batched)"
    )


# =============================================================================
# CHECKPOINT APPROVAL SCHEMAS (For our API responses)
# =============================================================================

class HITLApprovalRequest(BaseModel):
    """
    Request schema for approving/rejecting HITL checkpoints.
    
    Used by frontend when user approves or rejects checkpoint content.
    """
    feedback: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="Human feedback on the checkpoint (required for audit trail)"
    )
    is_approve: bool = Field(
        ...,
        description="True to approve and continue, False to reject and request revision"
    )


class HITLApprovalResponse(BaseModel):
    """
    Response after processing checkpoint approval/rejection.
    """
    status: str = Field(
        ...,
        description="Operation status (success, error)"
    )
    checkpoint_id: UUID = Field(
        ...,
        description="ID of the processed checkpoint"
    )
    execution_id: UUID = Field(
        ...,
        description="ID of the crew execution"
    )
    message: str = Field(
        ...,
        description="Human-readable status message"
    )
    crew_resumed: bool = Field(
        ...,
        description="Whether CrewAI execution was successfully resumed"
    )
    will_retry: Optional[bool] = Field(
        None,
        description="True if rejection means agent will retry the task"
    )


# =============================================================================
# CHECKPOINT RESPONSE SCHEMAS (For listing/getting checkpoints)
# =============================================================================

class CheckpointResponse(BaseModel):
    """Individual checkpoint details."""
    checkpoint_id: UUID
    execution_id: UUID
    checkpoint_type: str
    task_id: str
    content: str
    status: str
    created_at: datetime
    reviewed_at: Optional[datetime]
    reviewer_feedback: Optional[str]
    reviewed_by: Optional[UUID]
    checkpoint_metadata: Dict[str, Any]
    
    class Config:
        from_attributes = True


class PendingCheckpointsResponse(BaseModel):
    """Response for listing pending checkpoints."""
    checkpoints: List[CheckpointResponse]
    total: int
    limit: int
    offset: int