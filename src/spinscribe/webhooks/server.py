# =============================================================================
# SPINSCRIBE WEBHOOK SERVER
# FastAPI server for Human-in-the-Loop (HITL) approval workflow
# =============================================================================
"""
SpinScribe Webhook Server

This FastAPI server handles Human-in-the-Loop checkpoints in the content
creation workflow. It receives notifications from agents, stores workflow
state, presents content for review, and collects human feedback.

HITL Checkpoints:
1. Brand Voice Analysis (Task 2) - Approve/reject brand voice parameters
2. Style Compliance Review (Task 6) - Approve/reject style adherence
3. Final Quality Assurance (Task 7) - Final approval before delivery

Additional Webhooks:
4. Agent Activity - Real-time agent step updates
5. Task Status - Task completion notifications
6. Agent Completion - Agent finishes work
7. Error Notifications - Error and failure alerts

Run with:
    uvicorn spinscribe.webhooks.server:app --reload --port 8000
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any, List
from datetime import datetime
from pathlib import Path
import logging
import json
import uuid
import os

from spinscribe.webhooks.models import (
    WebhookPayload,
    ApprovalRequest,
    ApprovalResponse,
    WorkflowStatus,
    CheckpointType,
    ApprovalDecision
)
from spinscribe.webhooks.handlers import (
    handle_brand_voice_checkpoint,
    handle_style_compliance_checkpoint,
    handle_final_qa_checkpoint,
    process_approval_decision
)
from spinscribe.webhooks.storage import (
    workflow_storage,
    save_workflow_state,
    get_workflow_state,
    update_workflow_status,
    get_pending_approvals,
    cleanup_old_workflows
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# =============================================================================
# TEMPLATE SETUP
# =============================================================================

# Get the directory where this file is located
BASE_DIR = Path(__file__).resolve().parent

# Set up Jinja2 templates
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


# =============================================================================
# FASTAPI APPLICATION SETUP
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events.
    """
    # Startup
    logger.info("🚀 SpinScribe Webhook Server starting up...")
    logger.info("📋 Initializing workflow storage...")
    logger.info("🎨 Loading dashboard templates...")
    logger.info("✅ Server ready to handle HITL checkpoints")
    
    yield
    
    # Shutdown
    logger.info("🛑 SpinScribe Webhook Server shutting down...")
    logger.info("💾 Saving workflow states...")
    # Clean up resources if needed
    logger.info("✅ Shutdown complete")


app = FastAPI(
    title="SpinScribe Webhook Server",
    description="Human-in-the-Loop approval system for content creation workflow",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# HEALTH CHECK ENDPOINTS
# =============================================================================

@app.get("/", response_class=HTMLResponse)
async def root():
    """Root endpoint with server information."""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>SpinScribe Webhook Server</title>
        <style>
            body { font-family: Arial, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; }
            h1 { color: #2c3e50; }
            .status { background: #27ae60; color: white; padding: 10px; border-radius: 5px; }
            .endpoint { background: #ecf0f1; padding: 15px; margin: 10px 0; border-radius: 5px; }
            code { background: #34495e; color: #ecf0f1; padding: 2px 6px; border-radius: 3px; }
        </style>
    </head>
    <body>
        <h1>🚀 SpinScribe Webhook Server</h1>
        <div class="status">✅ Server is running</div>
        
        <h2>Available Endpoints</h2>
        
        <div class="endpoint">
            <h3>📊 Health Check</h3>
            <code>GET /health</code>
            <p>Check server status and statistics</p>
        </div>
        
        <div class="endpoint">
            <h3>📋 Review Dashboard</h3>
            <code>GET /dashboard</code>
            <p>Interactive dashboard for HITL approvals</p>
            <p><a href="/dashboard">🎯 Open Dashboard</a></p>
        </div>
        
        <div class="endpoint">
            <h3>📢 HITL Webhooks</h3>
            <code>POST /api/v1/webhook/hitl/brand-voice</code><br>
            <code>POST /api/v1/webhook/hitl/style-compliance</code><br>
            <code>POST /api/v1/webhook/hitl/final-qa</code>
            <p>Receive checkpoint notifications from agents</p>
        </div>
        
        <div class="endpoint">
            <h3>🔔 Activity Webhooks</h3>
            <code>POST /api/v1/webhook/agent-update</code><br>
            <code>POST /api/v1/webhook/task-status</code><br>
            <code>POST /api/v1/webhook/agent-completion</code><br>
            <code>POST /api/v1/webhook/error-notification</code>
            <p>Receive activity and status updates</p>
        </div>
        
        <div class="endpoint">
            <h3>✅ Approval Endpoints</h3>
            <code>GET /approvals/pending</code><br>
            <code>GET /workflows/{workflow_id}</code><br>
            <code>POST /approvals/{workflow_id}/submit</code>
            <p>Manage approval workflow</p>
        </div>
        
        <h2>Documentation</h2>
        <p>📖 <a href="/docs">Interactive API Documentation (Swagger UI)</a></p>
        <p>📘 <a href="/redoc">Alternative Documentation (ReDoc)</a></p>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@app.get("/health")
async def health_check():
    """
    Health check endpoint with server statistics.
    """
    pending_count = len(get_pending_approvals())
    total_workflows = len(workflow_storage._workflows)
    
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0",
        "statistics": {
            "total_workflows": total_workflows,
            "pending_approvals": pending_count,
            "active_workflows": sum(
                1 for w in workflow_storage._workflows.values() 
                if w["status"] == WorkflowStatus.IN_PROGRESS
            )
        }
    }


# =============================================================================
# DASHBOARD ENDPOINTS
# =============================================================================

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    """
    Serve the interactive HITL approval dashboard.
    
    This is the main UI where humans review and approve/reject content
    at various checkpoints in the workflow.
    """
    logger.info("📊 Dashboard accessed")
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.get("/approvals/pending")
async def get_pending_approvals_api():
    """
    Get list of all pending approvals for dashboard.
    
    Returns:
        List of pending approval requests with metadata
    """
    logger.info("📋 Fetching pending approvals")
    
    try:
        pending = get_pending_approvals()
        
        # Convert to dict format for JSON response
        result = []
        for approval in pending:
            workflow = get_workflow_state(approval.workflow_id)
            if not workflow:
                continue
                
            approval_request = workflow.get("approval_request", {})
            
            result.append({
                "workflow_id": approval.workflow_id,
                "checkpoint_type": approval.checkpoint.value,
                "checkpoint": approval.checkpoint.value,
                "client_name": approval.client_name,
                "topic": approval.topic,
                "created_at": approval.created_at,
                "approval_id": approval.approval_id,
                "title": approval_request.get("title", f"{approval.client_name} - {approval.topic}"),
                "description": approval_request.get("description", ""),
                "content": workflow.get("content", ""),
                "priority": approval_request.get("priority", "normal"),
                "questions": approval_request.get("questions", [])
            })
        
        logger.info(f"✅ Returning {len(result)} pending approvals")
        return result
        
    except Exception as e:
        logger.error(f"❌ Error fetching pending approvals: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/workflows/{workflow_id}")
async def get_workflow_details(workflow_id: str):
    """
    Get detailed information about a specific workflow.
    
    Used by dashboard modal to show full workflow details.
    """
    logger.info(f"🔍 Fetching workflow details: {workflow_id}")
    
    try:
        state = get_workflow_state(workflow_id)
        
        if not state:
            raise HTTPException(status_code=404, detail="Workflow not found")
        
        approval_request = state.get("approval_request", {})
        
        return {
            "workflow_id": workflow_id,
            "status": state["status"],
            "checkpoint_type": state["checkpoint_type"],
            "created_at": state["created_at"],
            "updated_at": state["updated_at"],
            "client_name": state.get("metadata", {}).get("client_name", "Unknown"),
            "topic": state.get("metadata", {}).get("topic", "Unknown"),
            "content_type": state.get("metadata", {}).get("content_type", "Unknown"),
            "audience": state.get("metadata", {}).get("audience", "Unknown"),
            "title": approval_request.get("title", ""),
            "description": approval_request.get("description", ""),
            "content": state.get("content", ""),
            "questions": approval_request.get("questions", []),
            "priority": approval_request.get("priority", "normal")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error fetching workflow details: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/approvals/{workflow_id}/submit")
async def submit_approval(workflow_id: str, response: ApprovalResponse):
    """
    Submit human approval decision for a workflow checkpoint.
    
    This endpoint:
    1. Updates workflow state in storage
    2. Processes the decision through handlers (for logging/audit)
    3. Returns next action information
    
    The crew AUTOMATICALLY RESUMES from the callback in crew.py
    when wait_for_approval() detects the status change.
    """
    logger.info(f"📝 Received approval decision for workflow: {workflow_id}")
    logger.info(f"   Decision: {response.decision}")
    logger.info(f"   Checkpoint: {response.checkpoint}")
    
    try:
        state = get_workflow_state(workflow_id)
        
        if not state:
            raise HTTPException(status_code=404, detail="Workflow not found")
        
        if state["status"] != WorkflowStatus.AWAITING_APPROVAL:
            raise HTTPException(
                status_code=400, 
                detail=f"Workflow not awaiting approval. Current status: {state['status']}"
            )
        
        # Process the approval decision (logging/audit only)
        result = await process_approval_decision(workflow_id, state, response)
        
        # Update workflow status based on decision
        if response.decision == ApprovalDecision.APPROVE:
            new_status = WorkflowStatus.APPROVED
            logger.info(f"✅ Workflow {workflow_id} approved - crew will auto-resume")
        elif response.decision == ApprovalDecision.REJECT:
            new_status = WorkflowStatus.REJECTED
            logger.warning(f"❌ Workflow {workflow_id} rejected")
        else:  # REVISE
            new_status = WorkflowStatus.REVISION_REQUESTED
            logger.info(f"🔄 Workflow {workflow_id} revision requested")
        
        # Update storage (this is what wait_for_approval() checks!)
        update_workflow_status(workflow_id, new_status)
        
        # Update state with approval response
        state["approval_response"] = response.dict()
        state["updated_at"] = datetime.utcnow().isoformat()
        
        return {
            "status": "success",
            "workflow_id": workflow_id,
            "decision": response.decision,
            "next_action": result.get("next_action"),
            "message": result.get("message"),
            "auto_resume": True,
            "note": "Crew will automatically resume from callback"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error processing approval: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# HITL WEBHOOK ENDPOINTS (Human-in-the-Loop Checkpoints)
# =============================================================================

@app.post("/api/v1/webhook/hitl/brand-voice")
async def brand_voice_webhook(payload: WebhookPayload, background_tasks: BackgroundTasks):
    """
    HITL Checkpoint 1: Brand Voice Analysis (Task 2)
    
    Called when brand_voice_specialist agent completes analysis and
    requires human approval before proceeding.
    """
    logger.info(f"📨 Received Brand Voice webhook for workflow: {payload.workflow_id}")
    
    try:
        # Process the checkpoint
        approval_request = await handle_brand_voice_checkpoint(payload)
        
        # Save workflow state
        save_workflow_state(
            workflow_id=payload.workflow_id,
            checkpoint_type=CheckpointType.BRAND_VOICE,
            content=payload.content,
            metadata=payload.metadata,
            approval_request=approval_request
        )
        
        logger.info(f"✅ Brand Voice checkpoint saved for workflow: {payload.workflow_id}")
        
        # Background task: cleanup old workflows
        background_tasks.add_task(cleanup_old_workflows, hours=24)
        
        return {
            "status": "received",
            "workflow_id": payload.workflow_id,
            "checkpoint": "brand_voice",
            "approval_id": approval_request.approval_id,
            "message": "Brand voice analysis ready for review",
            "review_url": f"/dashboard"
        }
        
    except Exception as e:
        logger.error(f"❌ Error processing brand voice webhook: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/webhook/hitl/style-compliance")
async def style_compliance_webhook(payload: WebhookPayload, background_tasks: BackgroundTasks):
    """
    HITL Checkpoint 2: Style Compliance Review (Task 6)
    
    Called when style_compliance_agent completes review and requires
    human approval before final QA.
    """
    logger.info(f"📨 Received Style Compliance webhook for workflow: {payload.workflow_id}")
    
    try:
        # Process the checkpoint
        approval_request = await handle_style_compliance_checkpoint(payload)
        
        # Save workflow state
        save_workflow_state(
            workflow_id=payload.workflow_id,
            checkpoint_type=CheckpointType.STYLE_COMPLIANCE,
            content=payload.content,
            metadata=payload.metadata,
            approval_request=approval_request
        )
        
        logger.info(f"✅ Style Compliance checkpoint saved for workflow: {payload.workflow_id}")
        
        background_tasks.add_task(cleanup_old_workflows, hours=24)
        
        return {
            "status": "received",
            "workflow_id": payload.workflow_id,
            "checkpoint": "style_compliance",
            "approval_id": approval_request.approval_id,
            "message": "Style compliance review ready for approval",
            "review_url": f"/dashboard"
        }
        
    except Exception as e:
        logger.error(f"❌ Error processing style compliance webhook: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/webhook/hitl/final-qa")
async def final_qa_webhook(payload: WebhookPayload, background_tasks: BackgroundTasks):
    """
    HITL Checkpoint 3: Final Quality Assurance (Task 7)
    
    Called when quality_assurance_editor completes final review and
    requires human approval before content delivery.
    """
    logger.info(f"📨 Received Final QA webhook for workflow: {payload.workflow_id}")
    
    try:
        # Process the checkpoint
        approval_request = await handle_final_qa_checkpoint(payload)
        
        # Save workflow state
        save_workflow_state(
            workflow_id=payload.workflow_id,
            checkpoint_type=CheckpointType.FINAL_QA,
            content=payload.content,
            metadata=payload.metadata,
            approval_request=approval_request
        )
        
        logger.info(f"✅ Final QA checkpoint saved for workflow: {payload.workflow_id}")
        
        background_tasks.add_task(cleanup_old_workflows, hours=24)
        
        return {
            "status": "received",
            "workflow_id": payload.workflow_id,
            "checkpoint": "final_qa",
            "approval_id": approval_request.approval_id,
            "message": "Final QA ready for approval",
            "review_url": f"/dashboard"
        }
        
    except Exception as e:
        logger.error(f"❌ Error processing final QA webhook: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# ACTIVITY WEBHOOK ENDPOINTS (Monitoring & Tracking)
# =============================================================================

@app.post("/api/v1/webhook/agent-update")
async def agent_update_webhook(payload: Dict[str, Any]):
    """
    Receive real-time agent activity updates.
    
    Called on every agent step/thought for real-time monitoring.
    """
    logger.info(f"🤖 Agent update: {payload.get('agent_name', 'Unknown')} - {payload.get('step_type', 'unknown')}")
    
    # Store activity for dashboard (implement as needed)
    # For now, just log it
    
    return {"status": "received", "message": "Agent update logged"}


@app.post("/api/v1/webhook/task-status")
async def task_status_webhook(payload: Dict[str, Any]):
    """
    Receive task completion notifications.
    
    Called when each task completes.
    """
    logger.info(f"📋 Task status: {payload.get('task_id', 'Unknown')} - {payload.get('status', 'unknown')}")
    
    # Log task completion
    workflow_id = payload.get('workflow_id') or payload.get('kickoff_id')
    if workflow_id:
        state = get_workflow_state(workflow_id)
        if state:
            if 'task_history' not in state:
                state['task_history'] = []
            state['task_history'].append({
                "task_id": payload.get('task_id'),
                "status": payload.get('status'),
                "timestamp": datetime.utcnow().isoformat()
            })
    
    return {"status": "received", "message": "Task status logged"}


@app.post("/api/v1/webhook/agent-completion")
async def agent_completion_webhook(payload: Dict[str, Any]):
    """
    Receive agent completion notifications.
    
    Called when crew execution completes.
    """
    logger.info(f"✅ Agent completion for workflow: {payload.get('workflow_id', 'Unknown')}")
    
    workflow_id = payload.get('workflow_id') or payload.get('kickoff_id')
    if workflow_id:
        update_workflow_status(workflow_id, WorkflowStatus.COMPLETED)
    
    return {"status": "received", "message": "Completion logged"}


@app.post("/api/v1/webhook/error-notification")
async def error_notification_webhook(payload: Dict[str, Any]):
    """
    Receive error and failure notifications.
    
    Called when errors occur during execution.
    """
    logger.error(f"❌ Error notification: {payload.get('error_type', 'Unknown')} - {payload.get('message', 'No message')}")
    
    workflow_id = payload.get('workflow_id') or payload.get('execution_id')
    if workflow_id:
        update_workflow_status(workflow_id, WorkflowStatus.FAILED)
    
    return {"status": "received", "message": "Error logged"}


# =============================================================================
# ERROR HANDLERS
# =============================================================================

@app.exception_handler(404)
async def not_found_handler(request: Request, exc: HTTPException):
    """Custom 404 handler."""
    return JSONResponse(
        status_code=404,
        content={
            "error": "Not Found",
            "message": "The requested resource was not found",
            "path": str(request.url)
        }
    )


@app.exception_handler(500)
async def internal_error_handler(request: Request, exc: Exception):
    """Custom 500 handler."""
    logger.error(f"Internal server error: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "message": "An unexpected error occurred",
            "details": str(exc) if os.getenv('DEBUG') == 'true' else "Contact support"
        }
    )


# =============================================================================
# RUN SERVER
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    
    print("=" * 80)
    print("🚀 STARTING SPINSCRIBE WEBHOOK SERVER")
    print("=" * 80)
    print("\n📋 Server Configuration:")
    print("   Host: 0.0.0.0")
    print("   Port: 8000")
    print("   Environment: Development")
    print("\n🔗 Access Points:")
    print("   Dashboard: http://localhost:8000/dashboard")
    print("   API Docs: http://localhost:8000/docs")
    print("   Health: http://localhost:8000/health")
    print("\n📋 Configured Webhooks:")
    print("   ✓ HITL: Brand Voice, Style Compliance, Final QA")
    print("   ✓ Activity: Agent Updates, Task Status, Completions")
    print("   ✓ Monitoring: Error Notifications")
    print("\n" + "=" * 80 + "\n")
    
    uvicorn.run(
        "spinscribe.webhooks.server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )