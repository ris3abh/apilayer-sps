# =============================================================================
# SPINSCRIBE WEBHOOK HANDLERS
# Business logic for processing HITL checkpoints
# =============================================================================
"""
Handlers for each type of HITL checkpoint in the workflow.

Each handler processes the webhook payload, extracts relevant information,
and creates an approval request for human review.

NOTE: In the callback-based HITL approach, crew resumption happens automatically
when the callback's wait_for_approval() function returns. These handlers only
need to process the checkpoint and create approval requests - NOT resume execution.
"""

from typing import Dict, Any
import uuid
import logging
from datetime import datetime

from spinscribe.webhooks.models import (
    WebhookPayload,
    ApprovalRequest,
    ApprovalResponse,
    CheckpointType,
    ApprovalDecision
)

logger = logging.getLogger(__name__)


# =============================================================================
# HELPER FUNCTIONS FOR ENUM/STRING HANDLING
# =============================================================================

def _get_checkpoint_value(checkpoint: Any) -> str:
    """
    Safely extract string value from checkpoint, whether it's enum or string.
    
    Args:
        checkpoint: CheckpointType enum or string
        
    Returns:
        String value of the checkpoint
    """
    if isinstance(checkpoint, CheckpointType):
        return checkpoint.value
    elif isinstance(checkpoint, str):
        return checkpoint
    else:
        return str(checkpoint)


def _get_decision_value(decision: Any) -> str:
    """
    Safely extract string value from decision, whether it's enum or string.
    
    Args:
        decision: ApprovalDecision enum or string
        
    Returns:
        String value of the decision
    """
    if isinstance(decision, ApprovalDecision):
        return decision.value
    elif isinstance(decision, str):
        return decision
    else:
        return str(decision)


def _ensure_checkpoint_enum(checkpoint: Any) -> CheckpointType:
    """
    Convert checkpoint to enum if it's a string.
    
    Args:
        checkpoint: CheckpointType enum or string
        
    Returns:
        CheckpointType enum
    """
    if isinstance(checkpoint, CheckpointType):
        return checkpoint
    elif isinstance(checkpoint, str):
        return CheckpointType(checkpoint)
    else:
        raise ValueError(f"Invalid checkpoint type: {checkpoint}")


def _ensure_decision_enum(decision: Any) -> ApprovalDecision:
    """
    Convert decision to enum if it's a string.
    
    Args:
        decision: ApprovalDecision enum or string
        
    Returns:
        ApprovalDecision enum
    """
    if isinstance(decision, ApprovalDecision):
        return decision
    elif isinstance(decision, str):
        return ApprovalDecision(decision)
    else:
        raise ValueError(f"Invalid decision type: {decision}")


# =============================================================================
# CHECKPOINT HANDLERS
# =============================================================================

async def handle_brand_voice_checkpoint(payload: WebhookPayload) -> ApprovalRequest:
    """
    Handle Brand Voice Analysis checkpoint (Task 2).
    
    Creates an approval request for the brand voice analysis,
    including the AI Language Code parameters and analysis details.
    
    Args:
        payload: Webhook payload with brand voice analysis content
    
    Returns:
        ApprovalRequest object for human review
    """
    logger.info(f"🎨 Processing Brand Voice checkpoint for workflow: {payload.workflow_id}")
    
    # Extract client and topic info
    client_name = payload.metadata.get('client_name', 'Unknown Client')
    topic = payload.metadata.get('topic', 'Unknown Topic')
    
    # Generate unique approval ID
    approval_id = f"appr_{uuid.uuid4().hex[:12]}"
    
    # Create approval request
    approval_request = ApprovalRequest(
        approval_id=approval_id,
        workflow_id=payload.workflow_id,
        checkpoint_type=CheckpointType.BRAND_VOICE,
        title=f"Brand Voice Analysis: {client_name} - {topic}",
        description=(
            "The Brand Voice Specialist has analyzed the client's existing content "
            "and generated AI Language Code parameters. Please review the analysis "
            "and approve if the parameters accurately capture the brand's voice."
        ),
        content=payload.content,
        questions=[
            "Do the AI Language Code parameters match the client's brand voice?",
            "Is the tone analysis accurate?",
            "Are the vocabulary and formality levels appropriate?"
        ],
        priority="high",
        created_at=datetime.utcnow().isoformat()
    )
    
    logger.info(f"✅ Created approval request: {approval_id}")
    logger.info(f"📊 Dashboard alert: Brand Voice Review needed for {client_name}")
    
    return approval_request


async def handle_style_compliance_checkpoint(payload: WebhookPayload) -> ApprovalRequest:
    """
    Handle Style Compliance Review checkpoint (Task 6).
    
    Creates an approval request for style compliance review,
    checking adherence to brand guidelines and style requirements.
    
    Args:
        payload: Webhook payload with style compliance report
    
    Returns:
        ApprovalRequest object for human review
    """
    logger.info(f"📝 Processing Style Compliance checkpoint for workflow: {payload.workflow_id}")
    
    client_name = payload.metadata.get('client_name', 'Unknown Client')
    topic = payload.metadata.get('topic', 'Unknown Topic')
    
    approval_id = f"appr_{uuid.uuid4().hex[:12]}"
    
    approval_request = ApprovalRequest(
        approval_id=approval_id,
        workflow_id=payload.workflow_id,
        checkpoint_type=CheckpointType.STYLE_COMPLIANCE,
        title=f"Style Compliance Review: {client_name} - {topic}",
        description=(
            "The Style Compliance Agent has reviewed content adherence to brand "
            "voice and style guidelines. Please approve if the content matches "
            "the approved brand voice parameters."
        ),
        content=payload.content,
        questions=[
            "Does the content match the approved brand voice?",
            "Are all style guidelines followed?",
            "Is the tone consistent throughout?"
        ],
        priority="medium",
        created_at=datetime.utcnow().isoformat()
    )
    
    logger.info(f"✅ Created approval request: {approval_id}")
    logger.info(f"📊 Dashboard alert: Style Compliance Review needed for {client_name}")
    
    return approval_request


async def handle_final_qa_checkpoint(payload: WebhookPayload) -> ApprovalRequest:
    """
    Handle Final Quality Assurance checkpoint (Task 7).
    
    Creates an approval request for final QA review before content delivery.
    This is the last checkpoint before the content is finalized.
    
    Args:
        payload: Webhook payload with final QA report
    
    Returns:
        ApprovalRequest object for human review
    """
    logger.info(f"✨ Processing Final QA checkpoint for workflow: {payload.workflow_id}")
    
    client_name = payload.metadata.get('client_name', 'Unknown Client')
    topic = payload.metadata.get('topic', 'Unknown Topic')
    
    approval_id = f"appr_{uuid.uuid4().hex[:12]}"
    
    approval_request = ApprovalRequest(
        approval_id=approval_id,
        workflow_id=payload.workflow_id,
        checkpoint_type=CheckpointType.FINAL_QA,
        title=f"Final QA: {client_name} - {topic} (Ready for Delivery)",
        description=(
            "The Quality Assurance Editor has completed final review. This is the "
            "last checkpoint before content delivery. Please provide final approval "
            "or request any last-minute changes."
        ),
        content=payload.content,
        questions=[
            "Is the content ready for publication?",
            "Are all quality standards met?",
            "Are there any last-minute changes needed?"
        ],
        priority="high",
        created_at=datetime.utcnow().isoformat()
    )
    
    logger.info(f"✅ Created approval request: {approval_id}")
    logger.info(f"📊 Dashboard alert: Final QA Review needed for {client_name}")
    
    return approval_request


# =============================================================================
# APPROVAL DECISION PROCESSOR
# =============================================================================

async def process_approval_decision(
    workflow_id: str,
    workflow_state: Dict[str, Any],
    response: ApprovalResponse
) -> Dict[str, Any]:
    """
    Process human approval decision and determine next action.
    
    IMPORTANT: In the callback-based approach, this function does NOT
    actually resume the crew. The crew resumes automatically when
    wait_for_approval() in crew.py returns after detecting the status change.
    
    This function only:
    1. Logs the decision
    2. Returns information about what should happen next
    
    The actual continuation happens in the callback function.
    
    Args:
        workflow_id: Workflow identifier
        workflow_state: Current workflow state
        response: Human approval response
    
    Returns:
        Dictionary with next action information (for logging/audit only)
    """
    # Safely extract checkpoint type and decision values
    checkpoint_type_value = workflow_state.get("checkpoint_type", "unknown")
    checkpoint_type = _ensure_checkpoint_enum(checkpoint_type_value)
    decision = _ensure_decision_enum(response.decision)
    
    logger.info(f"⚙️  Processing {_get_decision_value(decision)} decision for {_get_checkpoint_value(checkpoint_type)} checkpoint")
    logger.info(f"   Execution ID: {workflow_id}")
    
    # Log reviewer information for audit trail
    if response.reviewer_name:
        logger.info(f"   Reviewed by: {response.reviewer_name}")
    if response.comments:
        logger.info(f"   Comments: {response.comments[:100]}...")
    
    # Determine what should happen next (for information only)
    if decision == ApprovalDecision.APPROVE:
        result = _get_approval_info(checkpoint_type)
        logger.info(f"✅ Approved: {result['message']}")
    elif decision == ApprovalDecision.REJECT:
        result = _get_rejection_info(checkpoint_type, response)
        logger.warning(f"❌ Rejected: {result['message']}")
        logger.warning(f"   Issues to address: {len(response.specific_changes or [])} items")
    else:  # REVISE
        result = _get_revision_info(checkpoint_type, response)
        logger.info(f"🔄 Revision requested: {result['message']}")
    
    # Add crew resume status (for information - actual resume happens in callback)
    result["crew_resume_status"] = {
        "auto_resume": True,
        "message": "Crew will auto-resume from callback when wait_for_approval() returns"
    }
    
    return result


def _get_approval_info(checkpoint_type: CheckpointType) -> Dict[str, Any]:
    """Get information about what happens after approval."""
    next_actions = {
        CheckpointType.BRAND_VOICE: {
            "next_action": "proceed_to_content_strategy",
            "message": "Brand voice approved. Content Strategy task will begin.",
            "next_task": "content_strategy_task"
        },
        CheckpointType.STYLE_COMPLIANCE: {
            "next_action": "proceed_to_final_qa",
            "message": "Style compliance approved. Final QA task will begin.",
            "next_task": "final_quality_assurance_task"
        },
        CheckpointType.FINAL_QA: {
            "next_action": "deliver_content",
            "message": "Final QA approved. Content is ready for delivery.",
            "next_task": "content_delivery_task"
        }
    }
    
    return next_actions.get(checkpoint_type, {
        "next_action": "unknown",
        "message": "Approval recorded but next action unclear."
    })


def _get_rejection_info(
    checkpoint_type: CheckpointType,
    response: ApprovalResponse
) -> Dict[str, Any]:
    """Get information about what happens after rejection."""
    checkpoint_value = _get_checkpoint_value(checkpoint_type)
    
    restart_info = {
        "brand_voice": {
            "next_action": "restart_from_brand_voice",
            "message": "Rejected. Will restart from Brand Voice Analysis task.",
            "restart_task": "brand_voice_analysis_task"
        },
        "style_compliance": {
            "next_action": "restart_from_content_generation",
            "message": "Rejected. Will restart from Content Generation task.",
            "restart_task": "content_generation_task"
        },
        "final_qa": {
            "next_action": "restart_from_style_compliance",
            "message": "Rejected. Will restart from Style Compliance Review task.",
            "restart_task": "style_compliance_review_task"
        }
    }
    
    result = restart_info.get(checkpoint_value, {
        "next_action": "unknown",
        "message": "Rejection recorded but restart action unclear."
    })
    
    result["issues"] = response.specific_changes or []
    return result


def _get_revision_info(
    checkpoint_type: CheckpointType,
    response: ApprovalResponse
) -> Dict[str, Any]:
    """Get information about what happens after revision request."""
    checkpoint_value = _get_checkpoint_value(checkpoint_type)
    
    return {
        "next_action": f"revise_{checkpoint_value}",
        "message": f"Revision requested. {checkpoint_value.replace('_', ' ').title()} Agent will address issues.",
        "revision_items": response.specific_changes or [],
        "feedback": response.feedback
    }