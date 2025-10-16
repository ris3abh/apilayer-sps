# =============================================================================
# SPINSCRIBE WEBHOOK MODELS
# Pydantic models for webhook requests and responses
# =============================================================================
"""
Data models for the SpinScribe webhook system.

These Pydantic models define the structure for:
- Webhook payloads from agents
- Approval requests for human review
- Approval responses from humans
- Workflow status tracking
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum


# =============================================================================
# ENUMS
# =============================================================================

class CheckpointType(str, Enum):
    """Types of HITL checkpoints in the workflow."""
    BRAND_VOICE = "brand_voice"
    STYLE_COMPLIANCE = "style_compliance"
    FINAL_QA = "final_qa"


class ApprovalDecision(str, Enum):
    """Human approval decisions."""
    APPROVE = "approve"
    REJECT = "reject"
    REVISE = "revise"


class WorkflowStatus(str, Enum):
    """Workflow execution status."""
    IN_PROGRESS = "in_progress"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    REVISION_REQUESTED = "revision_requested"
    COMPLETED = "completed"
    FAILED = "failed"


# =============================================================================
# WEBHOOK PAYLOAD MODELS
# =============================================================================

class WebhookPayload(BaseModel):
    """
    Payload received from agents when reaching HITL checkpoint.
    
    This is what agents send to the webhook endpoint when they
    complete a task that requires human approval.
    """
    workflow_id: str = Field(
        ...,
        description="Unique identifier for this content creation workflow"
    )
    
    checkpoint_type: CheckpointType = Field(
        ...,
        description="Type of HITL checkpoint (brand_voice, style_compliance, final_qa)"
    )
    
    content: str = Field(
        ...,
        description="Content or analysis output that needs review"
    )
    
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context (client_name, topic, content_type, etc.)"
    )
    
    timestamp: Optional[str] = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="Timestamp when checkpoint was reached"
    )
    
    agent_name: Optional[str] = Field(
        None,
        description="Name of the agent that reached this checkpoint"
    )
    
    task_output: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Complete task output from the agent"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "workflow_id": "wf_abc123def456",
                "checkpoint_type": "brand_voice",
                "content": "# Brand Voice Analysis\n\nAI Language Code: /TN/A3,P4/VL4/SC3...",
                "metadata": {
                    "client_name": "TechCorp Solutions",
                    "topic": "AI in Healthcare",
                    "content_type": "blog",
                    "audience": "Healthcare professionals"
                },
                "agent_name": "brand_voice_specialist"
            }
        }


# =============================================================================
# APPROVAL REQUEST MODELS
# =============================================================================

class ApprovalRequest(BaseModel):
    """
    Request for human approval generated from webhook payload.
    
    This is what gets presented to human reviewers for decision.
    """
    approval_id: str = Field(
        ...,
        description="Unique identifier for this approval request"
    )
    
    workflow_id: str = Field(
        ...,
        description="Associated workflow ID"
    )
    
    checkpoint_type: CheckpointType = Field(
        ...,
        description="Type of checkpoint requiring approval"
    )
    
    title: str = Field(
        ...,
        description="Human-readable title for this approval"
    )
    
    description: str = Field(
        ...,
        description="Description of what needs to be reviewed"
    )
    
    content: str = Field(
        ...,
        description="Full content/analysis for review"
    )
    
    questions: List[str] = Field(
        default_factory=list,
        description="Specific questions for human reviewer"
    )
    
    options: List[str] = Field(
        default_factory=lambda: ["approve", "reject", "revise"],
        description="Available decision options"
    )
    
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context for reviewer"
    )
    
    created_at: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="When this approval request was created"
    )
    
    priority: Optional[str] = Field(
        "normal",
        description="Priority level (low, normal, high, urgent)"
    )


# =============================================================================
# APPROVAL RESPONSE MODELS
# =============================================================================

class ApprovalResponse(BaseModel):
    """
    Response from human reviewer with approval decision.
    
    This is what humans submit through the dashboard or API
    when making an approval decision.
    """
    decision: ApprovalDecision = Field(
        ...,
        description="Approval decision (approve/reject/revise)"
    )
    
    checkpoint: CheckpointType = Field(
        ...,
        description="Checkpoint type this decision is for"
    )
    
    feedback: str = Field(
        ...,
        description="Required feedback explaining the decision"
    )
    
    reviewer_name: Optional[str] = Field(
        None,
        description="Name of person making the decision"
    )
    
    comments: Optional[str] = Field(
        None,
        description="Additional comments (optional)"
    )
    
    specific_changes: Optional[List[str]] = Field(
        default_factory=list,
        description="List of specific changes requested (for reject/revise)"
    )
    
    timestamp: Optional[str] = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="When the decision was made"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "decision": "approve",
                "checkpoint": "brand_voice",
                "feedback": "The AI Language Code parameters are excellent!",
                "reviewer_name": "John Doe",
                "comments": "Great work on brand voice analysis",
                "specific_changes": []
            }
        }


# =============================================================================
# WORKFLOW STATE MODELS
# =============================================================================

class WorkflowState(BaseModel):
    """
    Complete state of a workflow for tracking.
    """
    workflow_id: str
    status: WorkflowStatus
    checkpoint_type: CheckpointType
    content: str
    metadata: Dict[str, Any]
    approval_request: ApprovalRequest
    approval_response: Optional[ApprovalResponse] = None
    created_at: str
    updated_at: str
    history: List[Dict[str, Any]] = Field(default_factory=list)


# =============================================================================
# RESPONSE MODELS
# =============================================================================

class WebhookAcknowledgment(BaseModel):
    """Response sent back to agent when webhook is received."""
    status: str = Field(..., description="Status of webhook receipt")
    workflow_id: str = Field(..., description="Workflow ID")
    checkpoint: str = Field(..., description="Checkpoint type")
    approval_id: str = Field(..., description="Generated approval ID")
    message: str = Field(..., description="Human-readable message")
    review_url: str = Field(..., description="URL to review this approval")


class ApprovalResult(BaseModel):
    """Result of processing an approval decision."""
    status: str = Field(..., description="Processing status")
    workflow_id: str = Field(..., description="Workflow ID")
    decision: ApprovalDecision = Field(..., description="Decision made")
    next_action: str = Field(..., description="What happens next")
    message: str = Field(..., description="Result message")


class PendingApprovalSummary(BaseModel):
    """Summary of a pending approval for list views."""
    workflow_id: str
    checkpoint: CheckpointType
    client_name: str
    topic: str
    created_at: str
    approval_id: str


class DashboardStats(BaseModel):
    """Statistics for dashboard display."""
    total_workflows: int
    pending_approvals: int
    active_workflows: int
    approved_today: int
    rejected_today: int