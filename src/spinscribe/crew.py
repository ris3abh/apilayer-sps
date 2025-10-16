#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SpinScribe Content Creation Crew - WITH HITL CHECKPOINTS

Multi-agent system with Human-in-the-Loop at 3 critical decision points:
1. Brand Voice Analysis - After agent analyzes brand voice
2. Style Compliance Review - After style guide verification
3. Final Quality Assurance - Before content delivery

Version: 4.0.0 - HITL Enabled
References:
- HITL Docs: https://docs.crewai.com/concepts/hitl-workflows
- Task Configuration: https://docs.crewai.com/core-concepts/tasks
"""

import os
import sys
from datetime import datetime
from typing import Dict, Any

from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task, before_kickoff
from crewai_tools import SerperDevTool

import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global execution tracking
_current_execution_id = None


# =============================================================================
# SPINSCRIBE CREW WITH HITL CHECKPOINTS
# =============================================================================

@CrewBase
class SpinscribeCrew:
    """
    SpinScribe Content Creation Crew with HITL Checkpoints
    
    7 specialized agents working sequentially with 3 human approval checkpoints:
    
    WORKFLOW:
    1. Content Research           → Agent completes
    2. Brand Voice Analysis       → Agent completes → 🔴 CHECKPOINT #1 (human reviews)
    3. Content Strategy           → Agent completes
    4. Content Generation         → Agent completes
    5. SEO Optimization           → Agent completes
    6. Style Compliance Review    → Agent completes → 🔴 CHECKPOINT #2 (human reviews)
    7. Final Quality Assurance    → Agent completes → 🔴 CHECKPOINT #3 (human approves)
    
    HITL CHECKPOINTS:
    - When crew reaches a task with human_input=True, it:
      1. Completes the task
      2. Sends webhook to backend with task output
      3. Enters "Pending Human Input" state
      4. Waits for backend to call /resume endpoint
    
    - Your backend receives the checkpoint at: /api/v1/webhook/hitl
    - User approves/rejects via: /api/v1/checkpoints/{id}/approve or /reject
    - Backend calls CrewAI resume endpoint to continue
    
    Reference: https://docs.crewai.com/concepts/hitl-workflows
    """
    
    agents_config = 'config/agents.yaml'
    tasks_config = 'config/tasks.yaml'

    def __init__(self):
        """Initialize the crew and validate environment."""
        super().__init__()
        self._validate_environment()
        
    def _validate_environment(self):
        """Validate required environment variables."""
        required_vars = ['OPENAI_API_KEY']
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        
        if missing_vars:
            logger.error(f"❌ Missing required environment variables: {', '.join(missing_vars)}")
            sys.exit(1)
        
        if not os.getenv('SERPER_API_KEY'):
            logger.warning("⚠️  SERPER_API_KEY not set - web search tools may not work optimally")
        
        logger.info("✅ Environment validation complete")

    # =========================================================================
    # INPUT PREPROCESSING - Workflow Mode Detection
    # =========================================================================
    
    @before_kickoff
    def prepare_workflow(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Detect workflow mode and enrich inputs before crew execution.
        
        Automatically determines whether to use CREATION or REVISION mode based
        on the presence of initial_draft input.
        
        Args:
            inputs: Raw input dictionary from API or CLI
            
        Returns:
            Enriched inputs with workflow mode and metadata
        """
        global _current_execution_id
        
        # Generate unique execution ID
        _current_execution_id = f"exec_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        logger.info("="*80)
        logger.info("🚀 SPINSCRIBE WORKFLOW WITH HITL CHECKPOINTS")
        logger.info("="*80)
        logger.info(f"🔗 Execution ID: {_current_execution_id}")
        
        # Extract initial draft
        initial_draft = inputs.get('initial_draft', '').strip()
        has_initial_draft = bool(initial_draft)
        
        # Determine workflow mode
        explicit_mode = inputs.get('workflow_mode', '').lower()
        
        if explicit_mode in ['revision', 'creation', 'refinement']:
            workflow_mode = 'revision' if explicit_mode in ['refinement', 'revision'] else 'creation'
        else:
            workflow_mode = 'revision' if has_initial_draft else 'creation'
        
        # Enrich inputs with mode and metadata
        inputs['workflow_mode'] = workflow_mode
        inputs['has_initial_draft'] = has_initial_draft
        
        if has_initial_draft:
            # Revision mode metadata
            inputs['draft_length'] = len(initial_draft)
            inputs['draft_word_count'] = len(initial_draft.split())
            inputs['draft_source'] = inputs.get('draft_source', 'human_provided')
            
            logger.info(f"📝 WORKFLOW MODE: REVISION")
            logger.info(f"   ├─ Draft Length: {inputs['draft_length']} characters")
            logger.info(f"   ├─ Word Count: {inputs['draft_word_count']} words")
            logger.info(f"   └─ Source: {inputs['draft_source']}")
        else:
            # Creation mode metadata
            inputs['draft_length'] = 0
            inputs['draft_word_count'] = 0
            inputs['initial_draft'] = ""
            inputs['draft_source'] = 'ai_generated'
            
            logger.info(f"✨ WORKFLOW MODE: CREATION")
            logger.info(f"   └─ Generating content from scratch")
        
        # Set defaults for optional fields
        inputs.setdefault('content_length', '1500')
        inputs.setdefault('ai_language_code', '/TN/A3,P4/VL4/SC3/FL2/LF3')
        inputs.setdefault('client_knowledge_directory', 
                         f"./knowledge/clients/{inputs.get('client_name', 'default')}")
        
        # Log configuration
        logger.info(f"🎯 Configuration:")
        logger.info(f"   ├─ Client: {inputs.get('client_name', 'N/A')}")
        logger.info(f"   ├─ Topic: {inputs.get('topic', 'N/A')}")
        logger.info(f"   ├─ Content Type: {inputs.get('content_type', 'N/A')}")
        logger.info(f"   ├─ Audience: {inputs.get('audience', 'N/A')}")
        logger.info(f"   └─ AI Language Code: {inputs.get('ai_language_code', 'N/A')}")
        logger.info("")
        logger.info("🔴 HITL CHECKPOINTS ENABLED:")
        logger.info("   ├─ Checkpoint #1: Brand Voice Analysis")
        logger.info("   ├─ Checkpoint #2: Style Compliance Review")
        logger.info("   └─ Checkpoint #3: Final Quality Assurance")
        logger.info("="*80)
        
        return inputs

    # =========================================================================
    # AGENTS - Matching agents.yaml exactly
    # =========================================================================

    @agent
    def content_researcher(self) -> Agent:
        """Content Research & Competitive Analysis Specialist"""
        return Agent(
            config=self.agents_config['content_researcher'],
            tools=[SerperDevTool()],
            verbose=True
        )

    @agent
    def brand_voice_specialist(self) -> Agent:
        """Brand Voice Analysis Expert"""
        return Agent(
            config=self.agents_config['brand_voice_specialist'],
            verbose=True
        )

    @agent
    def content_strategist(self) -> Agent:
        """Content Strategy & Planning Specialist"""
        return Agent(
            config=self.agents_config['content_strategist'],
            tools=[SerperDevTool()],
            verbose=True
        )

    @agent
    def content_writer(self) -> Agent:
        """Expert Content Writer & Brand Storyteller"""
        return Agent(
            config=self.agents_config['content_writer'],
            tools=[SerperDevTool()],
            verbose=True
        )

    @agent
    def seo_specialist(self) -> Agent:
        """SEO Optimization Specialist & Search Strategy Expert"""
        return Agent(
            config=self.agents_config['seo_specialist'],
            tools=[SerperDevTool()],
            verbose=True
        )

    @agent
    def style_compliance_agent(self) -> Agent:
        """Style Guidelines & Standards Enforcer"""
        return Agent(
            config=self.agents_config['style_compliance_agent'],
            verbose=True
        )

    @agent
    def quality_assurance_editor(self) -> Agent:
        """Senior Editorial Quality Assurance Specialist"""
        return Agent(
            config=self.agents_config['quality_assurance_editor'],
            verbose=True
        )

    # =========================================================================
    # TASKS - WITH HITL CHECKPOINTS
    # =========================================================================

    @task
    def content_research_task(self) -> Task:
        """Task 1: Content Research & Competitive Analysis"""
        return Task(
            config=self.tasks_config['content_research_task']
        )

    @task
    def brand_voice_analysis_task(self) -> Task:
        """
        Task 2: Brand Voice Analysis
        
        🔴 CHECKPOINT #1: Brand Voice Review
        
        After this task completes, CrewAI will:
        1. Send webhook to /api/v1/webhook/hitl with brand voice analysis
        2. Pause execution
        3. Wait for human approval/rejection
        4. Resume when backend calls /resume endpoint
        
        Human reviews: Brand voice parameters, tone accuracy, style guidelines
        """
        task_config = self.tasks_config['brand_voice_analysis_task'].copy()
        task_config['human_input'] = True  # 🔴 ENABLE HITL CHECKPOINT
        return Task(config=task_config)

    @task
    def content_strategy_task(self) -> Task:
        """Task 3: Content Strategy & Outline Creation"""
        return Task(
            config=self.tasks_config['content_strategy_task']
        )

    @task
    def content_generation_task(self) -> Task:
        """Task 4: Content Generation"""
        return Task(
            config=self.tasks_config['content_generation_task']
        )

    @task
    def seo_optimization_task(self) -> Task:
        """Task 5: SEO Optimization & Enhancement"""
        return Task(
            config=self.tasks_config['seo_optimization_task']
        )

    @task
    def style_compliance_review_task(self) -> Task:
        """
        Task 6: Style Compliance Review
        
        🔴 CHECKPOINT #2: Style Compliance Review
        
        After this task completes, CrewAI will:
        1. Send webhook to /api/v1/webhook/hitl with compliance report
        2. Pause execution
        3. Wait for human approval/rejection
        4. Resume when backend calls /resume endpoint
        
        Human reviews: Style adherence, brand consistency, formatting
        """
        task_config = self.tasks_config['style_compliance_review_task'].copy()
        task_config['human_input'] = True  # 🔴 ENABLE HITL CHECKPOINT
        return Task(config=task_config)

    @task
    def final_quality_assurance_task(self) -> Task:
        """
        Task 7: Final Quality Assurance
        
        🔴 CHECKPOINT #3: Final Approval
        
        After this task completes, CrewAI will:
        1. Send webhook to /api/v1/webhook/hitl with final content
        2. Pause execution
        3. Wait for human final approval
        4. Resume (and complete) when backend calls /resume endpoint
        
        Human reviews: Overall quality, accuracy, publication readiness
        """
        task_config = self.tasks_config['final_quality_assurance_task'].copy()
        task_config['human_input'] = True  # 🔴 ENABLE HITL CHECKPOINT
        return Task(config=task_config)

    # =========================================================================
    # CREW DEFINITION
    # =========================================================================

    @crew
    def crew(self) -> Crew:
        """
        Creates the SpinScribe crew with sequential workflow and HITL checkpoints.
        
        When deployed to CrewAI and kicked off with webhook URLs, the crew will:
        1. Execute tasks sequentially
        2. Pause at tasks with human_input=True
        3. Send webhooks to your backend
        4. Wait for resume calls
        5. Continue execution after approval
        
        Your backend must:
        - Receive webhooks at: /api/v1/webhook/hitl
        - Store checkpoints for user review
        - Call CrewAI /resume endpoint when approved
        - Re-provide webhook URLs in resume call
        
        Returns:
            Crew: Configured crew with 7 agents, 7 tasks, 3 HITL checkpoints
        """
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
        )


# =============================================================================
# MAIN EXECUTION FUNCTION
# =============================================================================

def run():
    """
    Entry point for the SpinScribe crew.
    
    IMPORTANT: When deploying to CrewAI, your backend will kickoff the crew
    with webhook URLs. This local run() is mainly for testing.
    
    For production with HITL:
    1. Deploy this crew to CrewAI
    2. Your backend calls /kickoff with humanInputWebhook config
    3. Crew executes and sends webhooks to your backend
    4. Users approve via your frontend
    5. Backend calls /resume to continue
    
    Reference: https://docs.crewai.com/deployment/kickoff-crew
    """
    try:
        # Initialize crew
        crew_instance = SpinscribeCrew()
        
        # Example inputs for local testing
        # In production, these come from your backend API
        inputs = {
            'client_name': 'Yanmar',
            'topic': 'The Future of AI in Agriculture and Robotics',
            'content_type': 'blog',
            'audience': 'Agricultural Business Executives and Technology Decision-Makers',
            'ai_language_code': '/TN/A3,P4,EMP2/VL4/SC3/FL2/LF3',
            'content_length': '2000',
            # For REVISION mode, uncomment:
            # 'initial_draft': 'Your existing draft content here...',
        }
        
        logger.info("🚀 Starting SpinScribe crew execution...")
        logger.info("")
        logger.info("⚠️  NOTE: HITL checkpoints require webhook configuration!")
        logger.info("   For local testing, crew will pause and wait for manual input.")
        logger.info("   In production, deploy to CrewAI and use backend kickoff.")
        logger.info("")
        
        # Execute crew
        result = crew_instance.crew().kickoff(inputs=inputs)
        
        logger.info("="*80)
        logger.info("✅ SPINSCRIBE EXECUTION COMPLETE")
        logger.info("="*80)
        logger.info(f"📊 Result preview: {str(result)[:200]}...")
        logger.info("="*80)
        
        return result
        
    except Exception as e:
        logger.error("="*80)
        logger.error("❌ SPINSCRIBE EXECUTION FAILED")
        logger.error("="*80)
        logger.error(f"Error: {str(e)}")
        logger.error("="*80)
        raise


# =============================================================================
# TRAINING AND TESTING FUNCTIONS
# =============================================================================

def train():
    """Train the crew for improved performance."""
    inputs = {
        "topic": "AI in Healthcare",
        "audience": "Healthcare Executives",
        "content_type": "blog",
        "client_name": "TestClient"
    }
    try:
        SpinscribeCrew().crew().train(
            n_iterations=int(sys.argv[1]),
            filename=sys.argv[2],
            inputs=inputs
        )
    except Exception as e:
        raise Exception(f"An error occurred while training the crew: {e}")


def replay():
    """Replay the crew execution from a specific task."""
    try:
        SpinscribeCrew().crew().replay(task_id=sys.argv[1])
    except Exception as e:
        raise Exception(f"An error occurred while replaying the crew: {e}")


def test():
    """Test the crew execution and returns the results."""
    inputs = {
        "topic": "Test Topic",
        "audience": "Test Audience",
        "content_type": "blog",
        "client_name": "TestClient"
    }
    try:
        SpinscribeCrew().crew().test(
            n_iterations=int(sys.argv[1]),
            openai_model_name=sys.argv[2],
            inputs=inputs
        )
    except Exception as e:
        raise Exception(f"An error occurred while testing the crew: {e}")


if __name__ == "__main__":
    run()