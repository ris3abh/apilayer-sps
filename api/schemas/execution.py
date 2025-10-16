# api/schemas/execution.py
"""
Execution Schemas - Request/response models for crew executions

These schemas define the API contract for starting, monitoring,
and managing crew executions.
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any, List
from datetime import datetime
from uuid import UUID
from enum import Enum


# =============================================================================
# ENUMS
# =============================================================================

class ExecutionStatusEnum(str, Enum):
    """Execution status values for API responses."""
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowModeEnum(str, Enum):
    """Workflow mode values."""
    CREATION = "creation"
    REVISION = "revision"
    REPURPOSE = "repurpose"


# =============================================================================
# START EXECUTION
# =============================================================================

class StartExecutionRequest(BaseModel):
    """
    Request to start a new crew execution.
    
    The project_id must exist and belong to a client owned by the user.
    """
    project_id: UUID = Field(
        ...,
        description="UUID of the project to create content for"
    )
    workflow_mode: WorkflowModeEnum = Field(
        default=WorkflowModeEnum.CREATION,
        description="Workflow mode: creation, revision, or repurpose"
    )
    
    # Optional parameters for revision/repurpose modes
    previous_output_s3_key: Optional[str] = Field(
        None,
        description="S3 key of previous output (required for revision/repurpose)"
    )
    revision_instructions: Optional[str] = Field(
        None,
        max_length=2000,
        description="Instructions for revision (required for revision mode)"
    )
    
    @validator('revision_instructions')
    def validate_revision_mode(cls, v, values):
        """Validate that revision mode has instructions."""
        if values.get('workflow_mode') == WorkflowModeEnum.REVISION and not v:
            raise ValueError('revision_instructions required when workflow_mode is revision')
        return v


class StartExecutionResponse(BaseModel):
    """Response after starting an execution."""
    execution_id: UUID = Field(..., description="UUID of the created execution")
    project_id: UUID = Field(..., description="UUID of the project")
    status: ExecutionStatusEnum = Field(..., description="Initial execution status")
    crewai_execution_id: Optional[str] = Field(
        None,
        description="CrewAI execution ID (kickoff_id)"
    )
    message: str = Field(..., description="Status message")
    stream_url: str = Field(
        ...,
        description="SSE stream URL for real-time updates"
    )


# =============================================================================
# EXECUTION STATUS
# =============================================================================

class ExecutionStatusResponse(BaseModel):
    """
    Execution status and progress information.
    """
    execution_id: UUID
    project_id: UUID
    status: ExecutionStatusEnum
    workflow_mode: WorkflowModeEnum
    
    # Timestamps
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    
    # Progress tracking
    current_task: Optional[str] = Field(
        None,
        description="Name of the current task being executed"
    )
    progress_percentage: Optional[int] = Field(
        None,
        ge=0,
        le=100,
        description="Estimated progress (0-100)"
    )
    
    # Checkpoint status
    pending_checkpoint: Optional[Dict[str, Any]] = Field(
        None,
        description="Pending HITL checkpoint details if awaiting approval"
    )
    
    # Error information
    error_message: Optional[str] = Field(
        None,
        description="Error message if execution failed"
    )
    
    # Performance metrics
    metrics: Dict[str, Any] = Field(
        default_factory=dict,
        description="Execution metrics (duration, token usage, etc.)"
    )
    
    # Connection info
    active_connections: int = Field(
        default=0,
        description="Number of active SSE connections watching this execution"
    )
    
    class Config:
        from_attributes = True


# =============================================================================
# MESSAGES / CHAT HISTORY
# =============================================================================

class MessageResponse(BaseModel):
    """
    Individual message in the execution chat history.
    """
    message_id: UUID = Field(..., description="Unique message identifier")
    timestamp: datetime = Field(..., description="When the message was created")
    
    # Sender information
    sender_type: str = Field(
        ...,
        description="Type of sender: 'agent', 'user', 'system'"
    )
    sender_name: str = Field(..., description="Name of the sender")
    
    # Message content
    activity_type: str = Field(
        ...,
        description="Activity type (e.g., MESSAGE, TASK_START, CHECKPOINT)"
    )
    content: str = Field(..., description="Message content")
    
    # Metadata
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional message metadata"
    )
    
    class Config:
        from_attributes = True


class MessagesResponse(BaseModel):
    """
    List of messages (chat history) for an execution.
    """
    execution_id: UUID
    messages: List[MessageResponse]
    total: int = Field(..., description="Total number of messages")
    has_more: bool = Field(
        default=False,
        description="Whether there are more messages to load"
    )


# =============================================================================
# EXECUTION LIST
# =============================================================================

class ExecutionListItem(BaseModel):
    """
    Abbreviated execution info for list views.
    """
    execution_id: UUID
    project_id: UUID
    project_name: str
    client_name: str
    status: ExecutionStatusEnum
    workflow_mode: WorkflowModeEnum
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    has_pending_checkpoint: bool = Field(
        default=False,
        description="Whether execution has a pending checkpoint"
    )
    
    class Config:
        from_attributes = True


class ExecutionListResponse(BaseModel):
    """
    Paginated list of executions.
    """
    executions: List[ExecutionListItem]
    total: int
    limit: int
    offset: int


# =============================================================================
# CANCEL EXECUTION
# =============================================================================

class CancelExecutionResponse(BaseModel):
    """Response after cancelling an execution."""
    execution_id: UUID
    status: ExecutionStatusEnum
    message: str = Field(..., description="Cancellation status message")
    crewai_cancelled: bool = Field(
        ...,
        description="Whether CrewAI execution was successfully cancelled"
    )


# =============================================================================
# SSE EVENT TYPES
# =============================================================================

class SSEEventType(str, Enum):
    """Types of SSE events sent to clients."""
    # Connection events
    CONNECTED = "connected"
    HEARTBEAT = "heartbeat"
    
    # Execution events
    STATUS = "status"
    MESSAGE = "message"
    
    # Checkpoint events
    CHECKPOINT = "checkpoint"
    APPROVAL = "approval"
    
    # Completion events
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SSEEvent(BaseModel):
    """
    Structure of SSE events sent to clients.
    
    This matches the format clients should expect from the SSE stream.
    """
    event: SSEEventType = Field(..., description="Event type")
    data: Dict[str, Any] = Field(..., description="Event data")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Event timestamp"
    )