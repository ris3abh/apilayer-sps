#!/usr/bin/env python
# =============================================================================
# SPINSCRIBE MAIN ENTRY POINT
# CLI interface for SpinScribe content creation crew
# =============================================================================
"""
SpinScribe Main Module

This module provides the command-line interface for running, training,
testing, and replaying the SpinScribe content creation crew.

Usage:
    crewai run              - Run the crew with interactive input
    crewai train -n 5       - Train the crew for 5 iterations
    crewai replay -t <id>   - Replay from specific task
    crewai test -n 3        - Test the crew for 3 iterations
"""

import sys
import os
import warnings
from datetime import datetime
from typing import Dict, Any
from pathlib import Path

# Suppress specific warnings
warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

# Import dotenv for environment variable management
from dotenv import load_dotenv

# Import the SpinScribe crew
from spinscribe.crew import SpinscribeCrew


# =============================================================================
# ENVIRONMENT VALIDATION
# =============================================================================

def validate_environment() -> bool:
    """
    Validate that all required environment variables are set.
    
    Returns:
        bool: True if all required variables are set, False otherwise
    """
    # Load environment variables from .env file
    load_dotenv()
    
    required_vars = {
        'OPENAI_API_KEY': 'OpenAI API key for GPT-4o',
        'SERPER_API_KEY': 'Serper.dev API key for web search'
    }
    
    missing_required = []
    
    print("\n" + "=" * 80)
    print("ENVIRONMENT VALIDATION")
    print("=" * 80)
    
    # Check required variables
    print("\n📋 Required Environment Variables:")
    for var, description in required_vars.items():
        value = os.getenv(var)
        if value:
            # Mask the API key for security
            masked_value = f"{value[:8]}...{value[-4:]}" if len(value) > 12 else "***"
            print(f"   ✓ {var}: {masked_value}")
        else:
            print(f"   ✗ {var}: NOT SET - {description}")
            missing_required.append(var)
    
    # Report validation results
    if missing_required:
        print("\n" + "=" * 80)
        print("❌ VALIDATION FAILED")
        print("=" * 80)
        print(f"\nMissing required environment variables: {', '.join(missing_required)}")
        print("\nPlease set these variables in your .env file:")
        print("   OPENAI_API_KEY=your_openai_api_key")
        print("   SERPER_API_KEY=your_serper_api_key")
        return False
    
    print("\n" + "=" * 80)
    print("✅ VALIDATION SUCCESSFUL")
    print("=" * 80)
    
    return True


# =============================================================================
# INPUT COLLECTION
# =============================================================================

def get_user_inputs(interactive: bool = True) -> Dict[str, Any]:
    """
    Collect inputs for content creation either interactively or using defaults.
    
    Args:
        interactive: If True, prompts user for input. If False, uses defaults.
        
    Returns:
        Dictionary containing all required inputs for crew execution
    """
    if not interactive:
        # Non-interactive mode with defaults
        client_name = "Demo Client"
        topic = "Artificial Intelligence in Modern Business"
        content_type = "blog"
        audience = "Business executives and technology decision makers"
        ai_language_code = "/TN/P3,A2/VL3/SC3/FL2/LF3"
        client_knowledge_directory = f"knowledge/clients/{client_name.replace(' ', '_').lower()}"
        
        return {
            'client_name': client_name,
            'topic': topic,
            'content_type': content_type,
            'audience': audience,
            'ai_language_code': ai_language_code,
            'client_knowledge_directory': client_knowledge_directory,
            'has_initial_draft': False,
            'initial_draft': "",
            'draft_source': "none",
            'workflow_mode': "creation"
        }
    
    # Interactive mode
    print("\n" + "="*80)
    print("SPINSCRIBE CONTENT CREATION - INPUT COLLECTION")
    print("="*80)
    print("\nPlease provide the following information:")
    print("(Press Enter to use default values shown in brackets)\n")
    
    client_name = input("Client Name [Demo Client]: ").strip() or "Demo Client"
    topic = input("Content Topic [Artificial Intelligence in Modern Business]: ").strip() or "Artificial Intelligence in Modern Business"
    
    print("\nContent Type Options: blog, landing_page, local_article")
    content_type = input("Content Type [blog]: ").strip() or "blog"
    
    audience = input("Target Audience [Business executives and technology decision makers]: ").strip() or "Business executives and technology decision makers"
    
    print("\nAI Language Code defines tone, vocabulary, and style.")
    print("Example: /TN/P3,A2/VL3/SC3/FL2/LF3")
    ai_language_code = input("AI Language Code [/TN/P3,A2/VL3/SC3/FL2/LF3]: ").strip() or "/TN/P3,A2/VL3/SC3/FL2/LF3"
    
    # Initial Draft (Optional) - for workflow mode detection
    print("\n📄 Initial Draft (Optional):")
    print("Do you have an initial draft to refine? [Y/n]: ", end="")
    has_draft = input().strip().lower() in ['y', 'yes', '']
    
    initial_draft = None
    draft_source = None
    
    if has_draft:
        print("\nHow would you like to provide the draft?")
        print("1. Paste text directly")
        print("2. Provide file path")
        print("3. Provide URL")
        draft_option = input("Choose option [1/2/3]: ").strip() or "1"
        
        if draft_option == "1":
            print("\nPaste your draft (press Ctrl+D or Ctrl+Z when done):")
            print("-" * 80)
            lines = []
            try:
                while True:
                    lines.append(input())
            except EOFError:
                pass
            initial_draft = "\n".join(lines)
            draft_source = "pasted_text"
            
        elif draft_option == "2":
            file_path = input("Enter file path: ").strip()
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    initial_draft = f.read()
                draft_source = f"file:{file_path}"
            except Exception as e:
                print(f"⚠️  Error reading file: {e}")
                print("Proceeding without initial draft...")
                has_draft = False
                
        elif draft_option == "3":
            url = input("Enter URL: ").strip()
            try:
                import requests
                response = requests.get(url, timeout=10)
                initial_draft = response.text
                draft_source = f"url:{url}"
            except Exception as e:
                print(f"⚠️  Error fetching URL: {e}")
                print("Proceeding without initial draft...")
                has_draft = False

    # Add client_knowledge_directory
    client_knowledge_directory = f"knowledge/clients/{client_name.replace(' ', '_').lower()}"
    
    inputs = {
        'client_name': client_name,
        'topic': topic,
        'content_type': content_type,
        'audience': audience,
        'ai_language_code': ai_language_code,
        'client_knowledge_directory': client_knowledge_directory,
        'has_initial_draft': has_draft,
        'initial_draft': initial_draft if has_draft else "",
        'draft_source': draft_source if has_draft else "none",
        'workflow_mode': "revision" if has_draft else "creation"
    }
    
    print("\n" + "="*80)
    print("INPUT SUMMARY")
    print("="*80)
    print(f"   Client Name: {client_name}")
    print(f"   Topic: {topic}")
    print(f"   Content Type: {content_type}")
    print(f"   Audience: {audience}")
    print(f"   AI Language Code: {ai_language_code}")
    print(f"   Knowledge Directory: {client_knowledge_directory}")
    print(f"   Workflow Mode: {'🔄 Revision (with draft)' if has_draft else '✨ Creation (from scratch)'}")
    if has_draft:
        print(f"   Draft Source: {draft_source}")
        print(f"   Draft Length: {len(initial_draft)} characters")
    print("="*80 + "\n")
    
    confirm = input("Proceed with these inputs? [Y/n]: ").strip().lower()
    if confirm and confirm not in ['y', 'yes', '']:
        print("Operation cancelled by user.")
        sys.exit(0)
    
    return inputs


# =============================================================================
# MAIN EXECUTION FUNCTIONS
# =============================================================================

def run():
    """
    Run the SpinScribe content creation crew.
    
    This function:
    1. Validates environment variables
    2. Collects user inputs
    3. Runs crew with automatic workflow mode detection
    4. Handles errors and displays results
    
    Usage:
        crewai run
        python -m spinscribe.main
    """
    try:
        print("\n" + "=" * 80)
        print("SPINSCRIBE CONTENT CREATION CREW")
        print("=" * 80)
        
        # Validate environment
        if not validate_environment():
            print("\n❌ Environment validation failed. Please fix the issues above.")
            sys.exit(1)
        
        # Determine if running interactively
        interactive = sys.stdout.isatty() and sys.stdin.isatty()
        
        # Collect inputs
        inputs = get_user_inputs(interactive=interactive)
        
        # Create output directory
        output_dir = Path(f"content_output/{inputs['client_name']}")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize crew
        print("\n🚀 Initializing SpinScribe Crew...")
        crew_instance = SpinscribeCrew()
        
        # Run crew
        print("\n▶️  Starting content creation...")
        print(f"    Mode: {inputs['workflow_mode'].upper()}")
        print(f"    Client: {inputs['client_name']}")
        print(f"    Topic: {inputs['topic']}\n")

        result = crew_instance.crew().kickoff(inputs=inputs)
        
        # Display results
        print("\n" + "=" * 80)
        print("✅ EXECUTION COMPLETE")
        print("=" * 80)
        print(f"\n✅ Content creation completed successfully!")
        
        # Save result to file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        result_file = output_dir / f"{inputs['content_type']}_{timestamp}.md"
        
        with open(result_file, 'w', encoding='utf-8') as f:
            f.write(str(result.raw))
        
        print(f"\n📄 Output saved to: {result_file}")
        
        # Display usage metrics if available
        if hasattr(result, 'token_usage') and result.token_usage:
            print(f"\n📊 Token Usage:")
            print(f"   {result.token_usage}")
        
        print("\n" + "=" * 80)
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Execution interrupted by user.")
        sys.exit(130)
    
    except Exception as e:
        print("\n" + "=" * 80)
        print("❌ ERROR DURING EXECUTION")
        print("=" * 80)
        print(f"\n{type(e).__name__}: {str(e)}")
        
        # Print full traceback in verbose mode
        if os.getenv('VERBOSE') == 'true':
            import traceback
            print("\n" + "=" * 80)
            print("FULL TRACEBACK")
            print("=" * 80)
            traceback.print_exc()
        
        sys.exit(1)


def train():
    """
    Train the SpinScribe crew with human feedback.
    
    This function:
    1. Runs the crew multiple times
    2. Collects human feedback after each iteration
    3. Uses feedback to improve agent performance
    
    Usage:
        crewai train -n 5 -f trained_data.pkl
        
    Args (from sys.argv):
        -n, --n_iterations: Number of training iterations (default: 5)
        -f, --filename: File to save training data (default: trained_agents_data.pkl)
    """
    try:
        print("\n" + "=" * 80)
        print("SPINSCRIBE CREW TRAINING MODE")
        print("=" * 80)
        
        # Validate environment
        if not validate_environment():
            print("\n❌ Environment validation failed. Please fix the issues above.")
            sys.exit(1)
        
        # Parse training parameters
        n_iterations = 5
        filename = "trained_agents_data.pkl"
        
        # Check command line arguments
        if len(sys.argv) > 1:
            try:
                n_iterations = int(sys.argv[1])
            except (ValueError, IndexError):
                print(f"⚠️  Invalid n_iterations parameter. Using default: {n_iterations}")
        
        if len(sys.argv) > 2:
            filename = sys.argv[2]
        
        print(f"\n📚 Training Configuration:")
        print(f"   Iterations: {n_iterations}")
        print(f"   Training File: {filename}")
        
        # Get training inputs
        inputs = get_user_inputs(interactive=False)
        
        print("\n🎓 Starting training process...")
        print("   You will be asked to provide feedback after each iteration.")
        print("   This feedback helps improve agent performance over time.\n")
        
        # Initialize and train crew
        crew_instance = SpinscribeCrew()
        
        crew_instance.crew().train(
            n_iterations=n_iterations,
            filename=filename,
            inputs=inputs
        )
        
        print("\n" + "=" * 80)
        print("✅ TRAINING COMPLETE")
        print("=" * 80)
        print(f"\n📊 Training data saved to: {filename}")
        print(f"   The crew has been trained for {n_iterations} iterations.")
        print(f"   Agent performance should improve in future executions.\n")
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Training interrupted by user.")
        sys.exit(130)
    
    except Exception as e:
        print("\n" + "=" * 80)
        print("❌ ERROR DURING TRAINING")
        print("=" * 80)
        print(f"\n{type(e).__name__}: {str(e)}")
        sys.exit(1)


def replay():
    """
    Replay crew execution from a specific task.
    
    This function:
    1. Loads previous execution state
    2. Replays from specified task ID
    3. Continues execution from that point
    
    Usage:
        crewai replay -t <task_id>
        crewai log-tasks-outputs  # To see available task IDs
        
    Args (from sys.argv):
        -t, --task_id: ID of the task to replay from
    """
    try:
        print("\n" + "=" * 80)
        print("SPINSCRIBE CREW REPLAY MODE")
        print("=" * 80)
        
        # Validate environment
        if not validate_environment():
            print("\n❌ Environment validation failed. Please fix the issues above.")
            sys.exit(1)
        
        # Get task ID from command line
        if len(sys.argv) < 2:
            print("\n❌ Error: Task ID is required for replay.")
            print("\nUsage:")
            print("   crewai replay -t <task_id>")
            print("\nTo view available task IDs:")
            print("   crewai log-tasks-outputs")
            sys.exit(1)
        
        task_id = sys.argv[1]
        
        print(f"\n🔄 Replaying execution from task: {task_id}")
        
        # Initialize crew and replay
        crew_instance = SpinscribeCrew()
        result = crew_instance.crew().replay(task_id=task_id)
        
        print("\n" + "=" * 80)
        print("✅ REPLAY COMPLETE")
        print("=" * 80)
        print(f"\n📄 Result:\n{result.raw}\n")
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Replay interrupted by user.")
        sys.exit(130)
    
    except Exception as e:
        print("\n" + "=" * 80)
        print("❌ ERROR DURING REPLAY")
        print("=" * 80)
        print(f"\n{type(e).__name__}: {str(e)}")
        
        if "task_id" in str(e).lower() or "not found" in str(e).lower():
            print("\nTip: Use 'crewai log-tasks-outputs' to view available task IDs.")
        
        sys.exit(1)


def test():
    """
    Test the SpinScribe crew and evaluate results.
    
    This function:
    1. Runs the crew multiple times with test inputs
    2. Evaluates consistency and quality
    3. Generates test report
    
    Usage:
        crewai test -n 3 -m gpt-4o-mini
        
    Args (from sys.argv):
        -n, --n_iterations: Number of test iterations (default: 3)
        -m, --model: LLM model to use for testing (default: gpt-4o-mini)
    """
    try:
        print("\n" + "=" * 80)
        print("SPINSCRIBE CREW TEST MODE")
        print("=" * 80)
        
        # Validate environment
        if not validate_environment():
            print("\n❌ Environment validation failed. Please fix the issues above.")
            sys.exit(1)
        
        # Parse test parameters
        n_iterations = 3
        model = "gpt-4o-mini"
        
        # Check command line arguments
        if len(sys.argv) > 1:
            try:
                n_iterations = int(sys.argv[1])
            except (ValueError, IndexError):
                print(f"⚠️  Invalid n_iterations parameter. Using default: {n_iterations}")
        
        if len(sys.argv) > 2:
            model = sys.argv[2]
        
        print(f"\n🧪 Test Configuration:")
        print(f"   Iterations: {n_iterations}")
        print(f"   Model: {model}")
        
        # Get test inputs
        inputs = {
            'client_name': 'Test Client',
            'topic': 'AI Testing and Quality Assurance',
            'content_type': 'blog',
            'audience': 'QA Engineers and Software Testers',
            'ai_language_code': '/TN/P3,A2/VL3/SC3/FL2/LF3',
            'client_knowledge_directory': 'knowledge/clients/test_client',
            'has_initial_draft': False,
            'initial_draft': "",
            'draft_source': "none",
            'workflow_mode': "creation"
        }
        
        print("\n🧪 Running tests...")
        
        # Initialize and test crew
        crew_instance = SpinscribeCrew()
        
        crew_instance.crew().test(
            n_iterations=n_iterations,
            openai_model_name=model,
            inputs=inputs
        )
        
        print("\n" + "=" * 80)
        print("✅ TESTING COMPLETE")
        print("=" * 80)
        print(f"\n📊 Crew tested for {n_iterations} iterations using {model}.")
        print(f"   Check the test results for quality and consistency metrics.\n")
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Testing interrupted by user.")
        sys.exit(130)
    
    except Exception as e:
        print("\n" + "=" * 80)
        print("❌ ERROR DURING TESTING")
        print("=" * 80)
        print(f"\n{type(e).__name__}: {str(e)}")
        sys.exit(1)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def show_help():
    """Display help information for the SpinScribe CLI."""
    help_text = """
╔═══════════════════════════════════════════════════════════════════════════╗
║                    SPINSCRIBE CONTENT CREATION CREW                        ║
║                    Multi-Agent Content Generation System                   ║
╚═══════════════════════════════════════════════════════════════════════════╝

DESCRIPTION:
    SpinScribe is an advanced AI-powered content creation system that uses
    specialized agents to produce publication-ready content matching client
    brand voice with dual workflow mode support.

WORKFLOW MODES:
    CREATION:  Build content from scratch (no initial draft)
    REVISION:  Enhance and refine existing draft content

COMMANDS:
    run              Run the content creation crew (default)
    train            Train the crew with human feedback
    replay           Replay execution from a specific task
    test             Test the crew and evaluate results

USAGE:
    crewai run                        # Interactive mode
    crewai train -n 5                 # Train for 5 iterations
    crewai replay -t <task_id>        # Replay from specific task
    crewai test -n 3 -m gpt-4o-mini  # Test with 3 iterations

ENVIRONMENT VARIABLES:
    Required:
        OPENAI_API_KEY               OpenAI API key for GPT-4o
        SERPER_API_KEY               Serper.dev API key for web search

WORKFLOW STAGES:
    1. Content Research           - Gather comprehensive information
    2. Brand Voice Analysis       - Validate voice parameters
    3. Content Strategy           - Create detailed outline
    4. Content Generation         - Write draft content
    5. SEO Optimization           - Enhance search performance
    6. Style Compliance           - Verify brand adherence
    7. Quality Assurance          - Final review and polish

EXAMPLES:
    # Run with interactive input (choose creation or revision mode)
    crewai run
    
    # Train the crew for better performance
    crewai train -n 10 -f my_training.pkl
    
    # View available task IDs for replay
    crewai log-tasks-outputs
    
    # Replay from specific task
    crewai replay -t abc123def456
    
    # Test crew consistency
    crewai test -n 5

DOCUMENTATION:
    For more information, visit: https://docs.crewai.com

SUPPORT:
    GitHub: https://github.com/joaomdmoura/crewai
    Discord: https://discord.com/invite/X4JWnZnxPb
"""
    print(help_text)


# =============================================================================
# ENTRY POINT
# =============================================================================

def main():
    """
    Main entry point for direct execution.
    
    Handles command routing and argument parsing.
    """
    # Check for help flag
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command in ['-h', '--help', 'help']:
            show_help()
            sys.exit(0)
    
    # Default to run command
    run()


if __name__ == "__main__":
    """
    Execute when running the module directly.
    
    Usage:
        python -m spinscribe.main
        python src/spinscribe/main.py
    """
    main()


# =============================================================================
# MODULE EXPORTS
# =============================================================================

__all__ = [
    'run',
    'train',
    'replay',
    'test',
    'validate_environment',
    'get_user_inputs',
]