# =============================================================================
# SPINSCRIBE WORKFLOW STORAGE
# Persistent storage for HITL approval workflow state
# =============================================================================
"""
Storage module for managing workflow state, approval requests, and audit logs.

This module provides persistent storage for:
- Workflow execution state across HITL checkpoints
- Pending approval requests awaiting human review
- Approval decisions and feedback history
- Workflow metadata and execution timeline

Storage Strategy:
- In-memory dictionary for development/testing
- Can be replaced with Redis/PostgreSQL for production
- Thread-safe operations with proper locking
- Automatic cleanup of old workflows (>30 days)
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from collections import defaultdict
import threading
import json
import logging
from pathlib import Path

from spinscribe.webhooks.models import (
    WorkflowStatus,
    CheckpointType,
    ApprovalDecision,
    ApprovalRequest,
    PendingApprovalSummary,
    DashboardStats
)

logger = logging.getLogger(__name__)


# =============================================================================
# IN-MEMORY STORAGE (Thread-Safe)
# =============================================================================

class WorkflowStorage:
    """
    Thread-safe in-memory storage for workflow state.
    
    This implementation uses Python dictionaries with threading locks
    for concurrent access. For production, replace with Redis or PostgreSQL.
    """
    
    def __init__(self):
        """Initialize storage with thread locks."""
        self._workflows: Dict[str, Dict[str, Any]] = {}
        self._approvals: Dict[str, ApprovalRequest] = {}
        self._lock = threading.RLock()
        logger.info("📦 Workflow storage initialized (in-memory)")
    
    def create_workflow(
        self,
        workflow_id: str,
        client_name: str,
        topic: str,
        content_type: str = "unknown",
        audience: str = "unknown",
        ai_language_code: str = ""
    ) -> Dict[str, Any]:
        """
        Create a new workflow entry.
        
        Args:
            workflow_id: Unique workflow identifier
            client_name: Client name
            topic: Content topic
            content_type: Type of content (blog, article, etc.)
            audience: Target audience
            ai_language_code: AI language code parameters
            
        Returns:
            Created workflow dictionary
        """
        with self._lock:
            workflow = {
                "workflow_id": workflow_id,
                "client_name": client_name,
                "topic": topic,
                "content_type": content_type,
                "audience": audience,
                "ai_language_code": ai_language_code,
                "status": WorkflowStatus.IN_PROGRESS.value,
                "current_checkpoint": None,
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
                "task_outputs": {},
                "approval_history": [],
                "content": "",
                "metadata": {},
                "approval_request": None
            }
            
            self._workflows[workflow_id] = workflow
            logger.info(f"✅ Created workflow: {workflow_id} for {client_name}")
            return workflow
    
    def get_workflow(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """
        Get workflow by ID.
        
        Args:
            workflow_id: Workflow identifier
        
        Returns:
            Workflow dict or None if not found
        """
        with self._lock:
            return self._workflows.get(workflow_id)
    
    def update_workflow(
        self,
        workflow_id: str,
        updates: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Update workflow fields.
        
        Args:
            workflow_id: Workflow identifier
            updates: Dictionary of fields to update
        
        Returns:
            Updated workflow or None if not found
        """
        with self._lock:
            workflow = self._workflows.get(workflow_id)
            if not workflow:
                logger.warning(f"⚠️ Workflow {workflow_id} not found for update")
                return None
            
            workflow.update(updates)
            workflow["updated_at"] = datetime.utcnow().isoformat()
            
            logger.debug(f"🔄 Updated workflow {workflow_id}: {list(updates.keys())}")
            return workflow
    
    def update_workflow_status(
        self,
        workflow_id: str,
        status: WorkflowStatus,
        checkpoint: Optional[CheckpointType] = None
    ) -> bool:
        """
        Update workflow status and current checkpoint.
        
        Args:
            workflow_id: Workflow identifier
            status: New workflow status
            checkpoint: Current checkpoint (if applicable)
        
        Returns:
            True if successful, False otherwise
        """
        with self._lock:
            workflow = self._workflows.get(workflow_id)
            if not workflow:
                return False
            
            workflow["status"] = status.value
            if checkpoint:
                workflow["current_checkpoint"] = checkpoint.value
            workflow["updated_at"] = datetime.utcnow().isoformat()
            
            logger.info(
                f"🔄 Workflow {workflow_id} status → {status.value}"
                f"{f' (checkpoint: {checkpoint.value})' if checkpoint else ''}"
            )
            return True
    
    def save_checkpoint_state(
        self,
        workflow_id: str,
        checkpoint_type: CheckpointType,
        content: str,
        metadata: Dict[str, Any],
        approval_request: ApprovalRequest
    ) -> bool:
        """
        Save workflow state at a checkpoint.
        
        This is called when an agent reaches a HITL checkpoint and
        requires human approval.
        
        Args:
            workflow_id: Workflow identifier
            checkpoint_type: Type of checkpoint
            content: Content to review
            metadata: Additional metadata
            approval_request: Approval request object
            
        Returns:
            True if successful
        """
        with self._lock:
            # Get or create workflow
            workflow = self._workflows.get(workflow_id)
            if not workflow:
                # Create new workflow from metadata
                workflow = self.create_workflow(
                    workflow_id=workflow_id,
                    client_name=metadata.get("client_name", "Unknown"),
                    topic=metadata.get("topic", "Unknown"),
                    content_type=metadata.get("content_type", "unknown"),
                    audience=metadata.get("audience", "unknown"),
                    ai_language_code=metadata.get("ai_language_code", "")
                )
            
            # Update workflow with checkpoint data
            workflow["content"] = content
            workflow["metadata"] = metadata
            workflow["checkpoint_type"] = checkpoint_type.value
            workflow["current_checkpoint"] = checkpoint_type.value
            workflow["status"] = WorkflowStatus.AWAITING_APPROVAL.value
            workflow["approval_request"] = approval_request.dict()
            workflow["updated_at"] = datetime.utcnow().isoformat()
            
            # Store approval request for quick lookup
            self._approvals[approval_request.approval_id] = approval_request
            
            logger.info(
                f"💾 Saved checkpoint state: {workflow_id} @ {checkpoint_type.value}"
            )
            return True
    
    def save_task_output(
        self,
        workflow_id: str,
        task_name: str,
        output: str
    ) -> bool:
        """
        Save output from a completed task.
        
        Args:
            workflow_id: Workflow identifier
            task_name: Task name
            output: Task output content
            
        Returns:
            True if successful
        """
        with self._lock:
            workflow = self._workflows.get(workflow_id)
            if not workflow:
                return False
            
            workflow["task_outputs"][task_name] = output
            workflow["updated_at"] = datetime.utcnow().isoformat()
            
            logger.debug(f"📝 Saved task output: {task_name} for {workflow_id}")
            return True
    
    def record_approval_decision(
        self,
        workflow_id: str,
        checkpoint: CheckpointType,
        decision: ApprovalDecision,
        feedback: Optional[str] = None
    ) -> bool:
        """
        Record an approval decision in workflow history.
        
        Args:
            workflow_id: Workflow identifier
            checkpoint: Checkpoint where decision was made
            decision: Approval decision
            feedback: Optional human feedback
        
        Returns:
            True if successful, False otherwise
        """
        with self._lock:
            workflow = self._workflows.get(workflow_id)
            if not workflow:
                return False
            
            approval_record = {
                "checkpoint": checkpoint.value,
                "decision": decision.value,
                "feedback": feedback,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            workflow["approval_history"].append(approval_record)
            workflow["updated_at"] = datetime.utcnow().isoformat()
            
            logger.info(
                f"✅ Recorded {decision.value} decision for workflow {workflow_id} "
                f"at {checkpoint.value} checkpoint"
            )
            return True
    
    def get_pending_approvals(self) -> List[PendingApprovalSummary]:
        """
        Get list of all pending approval requests.
        
        Returns:
            List of PendingApprovalSummary objects
        """
        with self._lock:
            summaries = []
            
            for approval_id, approval in self._approvals.items():
                workflow = self._workflows.get(approval.workflow_id)
                if not workflow:
                    continue
                
                # Only include workflows awaiting approval
                if workflow["status"] != WorkflowStatus.AWAITING_APPROVAL.value:
                    continue
                
                summary = PendingApprovalSummary(
                    workflow_id=approval.workflow_id,
                    checkpoint=approval.checkpoint_type,
                    client_name=workflow["client_name"],
                    topic=workflow["topic"],
                    created_at=approval.created_at,
                    approval_id=approval_id
                )
                summaries.append(summary)
            
            # Sort by creation time (oldest first)
            summaries.sort(key=lambda x: x.created_at)
            
            return summaries
    
    def cleanup_old_workflows(self, days: int = 30) -> int:
        """
        Clean up workflows older than specified days.
        
        Args:
            days: Retention period in days
            
        Returns:
            Number of workflows removed
        """
        with self._lock:
            cutoff = datetime.utcnow() - timedelta(days=days)
            cutoff_iso = cutoff.isoformat()
            
            to_remove = []
            for workflow_id, workflow in self._workflows.items():
                if workflow["updated_at"] < cutoff_iso:
                    to_remove.append(workflow_id)
            
            for workflow_id in to_remove:
                del self._workflows[workflow_id]
                logger.info(f"🗑️  Removed old workflow: {workflow_id}")
            
            if to_remove:
                logger.info(f"🧹 Cleaned up {len(to_remove)} old workflows")
            
            return len(to_remove)


# =============================================================================
# GLOBAL STORAGE INSTANCE
# =============================================================================

# Singleton instance for application-wide use
workflow_storage = WorkflowStorage()


# =============================================================================
# HELPER FUNCTIONS (Convenience Wrappers)
# =============================================================================

def save_workflow_state(
    workflow_id: str,
    checkpoint_type: CheckpointType,
    content: str,
    metadata: Dict[str, Any],
    approval_request: ApprovalRequest
) -> bool:
    """
    Convenience function to save checkpoint state.
    
    This is the main function called by webhook endpoints.
    
    Args:
        workflow_id: Workflow identifier
        checkpoint_type: Type of checkpoint
        content: Content to review
        metadata: Additional metadata
        approval_request: Approval request object
    
    Returns:
        True if successful
    """
    return workflow_storage.save_checkpoint_state(
        workflow_id=workflow_id,
        checkpoint_type=checkpoint_type,
        content=content,
        metadata=metadata,
        approval_request=approval_request
    )


def get_workflow_state(workflow_id: str) -> Optional[Dict[str, Any]]:
    """
    Convenience function to get workflow.
    
    Args:
        workflow_id: Workflow identifier
    
    Returns:
        Workflow dict or None
    """
    return workflow_storage.get_workflow(workflow_id)


def update_workflow_status(
    workflow_id: str,
    status: WorkflowStatus,
    checkpoint: Optional[CheckpointType] = None
) -> bool:
    """
    Convenience function to update workflow status.
    
    Args:
        workflow_id: Workflow identifier
        status: New status
        checkpoint: Current checkpoint
    
    Returns:
        True if successful
    """
    return workflow_storage.update_workflow_status(workflow_id, status, checkpoint)


def get_pending_approvals() -> List[PendingApprovalSummary]:
    """
    Convenience function to get pending approvals.
    
    Returns:
        List of pending approval summaries
    """
    return workflow_storage.get_pending_approvals()


def cleanup_old_workflows(hours: int = 24) -> int:
    """
    Convenience function to cleanup old workflows.
    
    Args:
        hours: Retention period in hours (converted to days)
    
    Returns:
        Number of workflows removed
    """
    days = hours // 24
    if days < 1:
        days = 1
    return workflow_storage.cleanup_old_workflows(days)