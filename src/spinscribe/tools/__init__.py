# =============================================================================
# SPINSCRIBE TOOLS PACKAGE
# Custom tools for content creation workflow
# =============================================================================
"""
SpinScribe Custom Tools Package

This package provides specialized tools for the multi-agent content creation
system, including AI Language Code parsing, brand voice analysis utilities,
and other content creation support tools.

Available Tools:
- ai_language_code_parser: Parse AI Language Code shorthand into guidelines
- parse_ai_language_code: Utility function for direct code parsing
- validate_ai_language_code: Validate AI Language Code format
- generate_example_code: Generate valid AI Language Code from parameters
"""

from spinscribe.tools.custom_tool import (
    # Tool class
    AILanguageCodeParser,
    
    # Tool instance (ready to use)
    ai_language_code_parser,
    
    # Utility functions
    parse_ai_language_code,
    validate_ai_language_code,
    generate_example_code,
)

# Define package exports
__all__ = [
    # Tool class
    'AILanguageCodeParser',
    
    # Tool instance
    'ai_language_code_parser',
    
    # Utility functions
    'parse_ai_language_code',
    'validate_ai_language_code',
    'generate_example_code',
]

# Package metadata
__version__ = '0.1.0'
__author__ = 'Rishabh Sharma'
__description__ = 'Custom tools for SpinScribe multi-agent content creation system'