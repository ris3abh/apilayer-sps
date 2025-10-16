# api/services/crewai.py
"""
CrewAI Service - Integration with CrewAI AMP Platform

This service handles all communication with the CrewAI API, including:
- Starting crew executions (kickoff)
- Resuming after HITL checkpoints
- Checking execution status
- Cancelling executions

CRITICAL IMPLEMENTATION NOTES:
1. Webhook URLs must be provided in BOTH kickoff and resume calls
2. CrewAI does NOT persist webhook configurations between calls
3. All webhook events use the same authentication token

References:
- HITL Workflows: https://docs.crewai.com/concepts/hitl-workflows
- Webhook Streaming: https://docs.crewai.com/concepts/webhook-streaming  
- Kickoff API: https://docs.crewai.com/deployment/kickoff-crew
"""

import httpx
from typing import Dict, Any, List, Optional
from api.config import settings
import logging

logger = logging.getLogger(__name__)


class CrewAIService:
    """Service for interacting with CrewAI AMP API."""
    
    # Complete list of supported events from CrewAI documentation
    # Source: https://docs.crewai.com/concepts/webhook-streaming#supported-events
    ALL_EVENTS = [
        # Crew Events
        "crew_kickoff_started",
        "crew_kickoff_completed",
        "crew_kickoff_failed",
        
        # Task Events
        "task_started",
        "task_completed",
        "task_failed",
        
        # Agent Events
        "agent_execution_started",
        "agent_execution_completed",
        "agent_execution_error",
        
        # LLM Events
        "llm_call_started",
        "llm_call_completed",
        "llm_call_failed",
        "llm_stream_chunk",
        
        # Tool Events
        "tool_usage_started",
        "tool_usage_finished",
        "tool_usage_error",
        
        # Memory Events
        "memory_query_started",
        "memory_query_completed",
        "memory_save_started",
        "memory_save_completed",
        
        # Knowledge Events
        "knowledge_query_started",
        "knowledge_query_completed",
    ]
    
    def __init__(self):
        self.base_url = settings.CREWAI_API_URL
        self.bearer_token = settings.CREWAI_BEARER_TOKEN
        self.webhook_base_url = settings.API_BASE_URL
        self.webhook_secret = settings.WEBHOOK_SECRET_TOKEN
        
        # Validate configuration
        if not self.base_url:
            raise ValueError("CREWAI_API_URL is not configured")
        if not self.bearer_token:
            raise ValueError("CREWAI_BEARER_TOKEN is not configured")
        if not self.webhook_secret or self.webhook_secret == "dev-secret":
            logger.warning("⚠️  Using default webhook secret! Generate a secure token for production.")
    
    def _get_headers(self) -> Dict[str, str]:
        """
        Get authorization headers for CrewAI API.
        
        Returns:
            Dict with Authorization and Content-Type headers
        """
        return {
            "Authorization": f"Bearer {self.bearer_token}",
            "Content-Type": "application/json"
        }
    
    def _get_webhook_config(self) -> Dict[str, Any]:
        """
        Get webhook configuration for event streaming.
        
        This configuration must be included in BOTH kickoff and resume calls.
        
        Format per CrewAI Webhook Streaming docs:
        https://docs.crewai.com/concepts/webhook-streaming#usage
        
        Returns:
            Dict with webhooks configuration
        """
        return {
            "events": self.ALL_EVENTS,  # Subscribe to all events
            "url": f"{self.webhook_base_url}/api/v1/webhook/stream",
            "realtime": False,  # Batch mode for better performance
            "authentication": {
                "strategy": "bearer",
                "token": self.webhook_secret
            }
        }
    
    def _get_hitl_webhook_config(self) -> Dict[str, Any]:
        """
        Get HITL webhook configuration for human-in-the-loop checkpoints.
        
        This configuration must be included in BOTH kickoff and resume calls.
        
        Format per CrewAI HITL Workflows docs:
        https://docs.crewai.com/concepts/hitl-workflows#step-2-provide-webhook-url
        
        Returns:
            Dict with humanInputWebhook configuration
        """
        return {
            "url": f"{self.webhook_base_url}/api/v1/webhook/hitl",
            "authentication": {
                "strategy": "bearer",
                "token": self.webhook_secret
            }
        }
    
    async def kickoff_crew(
        self,
        inputs: Dict[str, Any],
        execution_id: str
    ) -> Dict[str, Any]:
        """
        Start a CrewAI crew execution.
        
        This method initiates a new crew execution with the provided inputs
        and configures webhooks for both event streaming and HITL checkpoints.
        
        Reference: https://docs.crewai.com/deployment/kickoff-crew#step-2-kickoff-execution
        
        Args:
            inputs: Input parameters for the crew (topic, client_name, etc.)
            execution_id: Our internal execution ID for tracking (stored in metadata)
        
        Returns:
            Dict containing:
                - kickoff_id: CrewAI's execution identifier
                - status: Initial status (typically "running")
        
        Raises:
            httpx.HTTPError: If CrewAI API request fails
        """
        logger.info(f"🚀 Initiating CrewAI kickoff for execution: {execution_id}")
        logger.debug(f"Inputs: {inputs}")
        
        # Build payload according to CrewAI API specification
        payload = {
            "inputs": inputs,
            
            # HITL Webhook Configuration
            # Source: https://docs.crewai.com/concepts/hitl-workflows
            "humanInputWebhook": self._get_hitl_webhook_config(),
            
            # Event Streaming Webhook Configuration  
            # Source: https://docs.crewai.com/concepts/webhook-streaming
            "webhooks": self._get_webhook_config(),
        }
        
        logger.debug(f"Webhook URLs configured:")
        logger.debug(f"  - HITL: {payload['humanInputWebhook']['url']}")
        logger.debug(f"  - Stream: {payload['webhooks']['url']}")
        logger.debug(f"  - Events: {len(payload['webhooks']['events'])} subscribed")
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/kickoff",
                    json=payload,
                    headers=self._get_headers()
                )
                response.raise_for_status()
                
                result = response.json()
                kickoff_id = result.get("kickoff_id")
                
                logger.info(f"✅ Crew kickoff successful! kickoff_id: {kickoff_id}")
                return result
                
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ CrewAI kickoff failed with status {e.response.status_code}")
            logger.error(f"Response: {e.response.text}")
            raise
        except httpx.RequestError as e:
            logger.error(f"❌ CrewAI request failed: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"❌ Unexpected error during kickoff: {str(e)}")
            raise
    
    async def resume_crew(
        self,
        crewai_execution_id: str,
        task_id: str,
        human_feedback: str,
        is_approve: bool
    ) -> Dict[str, Any]:
        """
        Resume a crew execution after HITL checkpoint approval/rejection.
        
        CRITICAL: Webhook URLs MUST be re-provided in every resume call.
        CrewAI does NOT persist webhook configurations from the kickoff call.
        
        Citation from docs:
        "You must provide the same webhook URLs in the resume call that you 
        used in the kickoff call. Webhook configurations are NOT automatically 
        carried over from kickoff."
        
        Source: https://docs.crewai.com/concepts/hitl-workflows#step-5-submit-human-feedback
        
        Args:
            crewai_execution_id: The kickoff_id from CrewAI
            task_id: The task ID from the HITL webhook payload
            human_feedback: User's feedback/comments on the checkpoint
            is_approve: True to approve, False to reject and request revision
        
        Returns:
            Dict containing resume confirmation
        
        Raises:
            httpx.HTTPError: If CrewAI API request fails
        """
        logger.info(f"🔄 Resuming CrewAI execution: {crewai_execution_id}")
        logger.info(f"   Task: {task_id}")
        logger.info(f"   Action: {'APPROVE' if is_approve else 'REJECT'}")
        logger.debug(f"   Feedback: {human_feedback}")
        
        # Build payload according to CrewAI API specification
        payload = {
            "execution_id": crewai_execution_id,
            "task_id": task_id,
            "human_feedback": human_feedback,
            "is_approve": is_approve,
            
            # 🚨 CRITICAL: Re-provide webhook configurations
            # CrewAI does NOT store these from the kickoff call!
            "humanInputWebhook": self._get_hitl_webhook_config(),
            "webhooks": self._get_webhook_config(),
        }
        
        logger.debug("⚠️  Re-providing webhook URLs (required for continued notifications)")
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/resume",
                    json=payload,
                    headers=self._get_headers()
                )
                response.raise_for_status()
                
                result = response.json()
                logger.info(f"✅ Crew resume successful!")
                
                if not is_approve:
                    logger.info("   Agent will retry task with feedback")
                
                return result
                
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ CrewAI resume failed with status {e.response.status_code}")
            logger.error(f"Response: {e.response.text}")
            raise
        except httpx.RequestError as e:
            logger.error(f"❌ CrewAI request failed: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"❌ Unexpected error during resume: {str(e)}")
            raise
    
    async def get_status(self, crewai_execution_id: str) -> Dict[str, Any]:
        """
        Get the current status of a crew execution.
        
        Reference: https://docs.crewai.com/deployment/kickoff-crew#step-3-check-execution-status
        
        Args:
            crewai_execution_id: The kickoff_id from CrewAI
        
        Returns:
            Dict containing execution status and progress information
        
        Raises:
            httpx.HTTPError: If CrewAI API request fails
        """
        logger.debug(f"📊 Checking status for execution: {crewai_execution_id}")
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.base_url}/status/{crewai_execution_id}",
                    headers=self._get_headers()
                )
                response.raise_for_status()
                
                status_data = response.json()
                logger.debug(f"Status: {status_data.get('status')}")
                
                return status_data
                
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.error(f"❌ Execution not found: {crewai_execution_id}")
            else:
                logger.error(f"❌ Status check failed with status {e.response.status_code}")
                logger.error(f"Response: {e.response.text}")
            raise
        except httpx.RequestError as e:
            logger.error(f"❌ Status check request failed: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"❌ Unexpected error during status check: {str(e)}")
            raise
    
    async def cancel_execution(self, crewai_execution_id: str) -> bool:
        """
        Cancel a running crew execution.
        
        Note: This may not be supported by all CrewAI deployments.
        Check your CrewAI instance capabilities.
        
        Args:
            crewai_execution_id: The kickoff_id from CrewAI
        
        Returns:
            True if cancellation successful, False otherwise
        """
        logger.info(f"🛑 Attempting to cancel execution: {crewai_execution_id}")
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.base_url}/cancel/{crewai_execution_id}",
                    headers=self._get_headers()
                )
                response.raise_for_status()
                
                logger.info(f"✅ Execution cancelled successfully")
                return True
                
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"⚠️  Execution not found: {crewai_execution_id}")
            elif e.response.status_code == 405:
                logger.warning(f"⚠️  Cancellation not supported by CrewAI instance")
            else:
                logger.error(f"❌ Cancellation failed with status {e.response.status_code}")
            return False
        except httpx.RequestError as e:
            logger.error(f"❌ Cancellation request failed: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"❌ Unexpected error during cancellation: {str(e)}")
            return False


# Dependency for FastAPI routes
def get_crewai_service() -> CrewAIService:
    """
    FastAPI dependency to get CrewAI service instance.
    
    Usage in routes:
        @router.post("/executions/start")
        async def start_execution(
            service: CrewAIService = Depends(get_crewai_service)
        ):
            result = await service.kickoff_crew(inputs, execution_id)
    """
    return CrewAIService()