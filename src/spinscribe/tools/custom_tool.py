# =============================================================================
# SPINSCRIBE CUSTOM TOOLS
# AI Language Code Parser and Utility Functions
# =============================================================================
"""
Custom tools for the SpinScribe content creation system.

This module provides specialized tools for parsing AI Language Code parameters,
analyzing brand voice, and supporting the multi-agent workflow.
"""

from crewai.tools import BaseTool
from typing import Type, Dict, Any, Optional, List, ClassVar
from pydantic import BaseModel, Field
import re
import json


# =============================================================================
# AI LANGUAGE CODE PARSER TOOL
# =============================================================================

class AILanguageCodeInput(BaseModel):
    """Input schema for AI Language Code Parser."""
    code: str = Field(
        ...,
        description="AI Language Code string to parse (e.g., /TN/A3,P4,EMP2/VL4/SC3/FL2/LF3)"
    )


class AILanguageCodeParser(BaseTool):
    """
    AI Language Code Parser Tool
    
    (docstring unchanged...)
    """
    
    name: str = "AI Language Code Parser"
    description: str = (
        "Parse AI Language Code shorthand (e.g., /TN/A3,P4/VL4/SC3) into detailed "
        "content creation parameters. Returns comprehensive guidelines for tone, "
        "vocabulary, sentence structure, and style."
    )
    args_schema: Type[BaseModel] = AILanguageCodeInput
    
    # Tone code mappings - NOW PROPERLY ANNOTATED
    TONE_CODES: ClassVar[Dict[str, str]] = {
        'A': 'Authoritative',
        'AF': 'Affluent',
        'AP': 'Approachable',
        'B': 'Bold',
        'BU': 'Bubbly',
        'C': 'Compassionate',
        'CB': 'Cerebral',
        'CH': 'Challenging',
        'EL': 'Elegant',
        'EM': 'Empowering',
        'EMP': 'Empathetic',
        'EN': 'Energetic',
        'ENC': 'Encouraging',
        'ET': 'Enthusiastic',
        'F': 'Friendly',
        'FA': 'Familiar',
        'H': 'Humorous',
        'HE': 'Helpful',
        'HF': 'Heartfelt',
        'I': 'Inspirational',
        'K': 'Knowledgeable',
        'L': 'Learning',
        'N': 'Neutral',
        'O': 'Optimistic',
        'P': 'Professional',
        'R': 'Refined',
        'S': 'Sincere',
        'SO': 'Sophisticated',
        'SU': 'Supportive',
        'T': 'Thoughtful',
        'TH': 'Thrilling',
        'U': 'Urgent',
        'V': 'Vibrant',
        'W': 'Whimsical',
        'X': 'Exclusive',
        'Y': 'Youthful'
    }
    
    def _run(self, code: str) -> str:
        """
        Parse AI Language Code and return detailed parameters.
        
        Args:
            code: AI Language Code string (e.g., /TN/A3,P4,EMP2/VL4/SC3/FL2/LF3)
        
        Returns:
            JSON string with parsed parameters and detailed guidelines
        """
        try:
            parsed = self._parse_code(code)
            guidelines = self._generate_guidelines(parsed)
            
            result = {
                "code": code,
                "parsed_parameters": parsed,
                "detailed_guidelines": guidelines,
                "summary": self._generate_summary(parsed)
            }
            
            return json.dumps(result, indent=2)
            
        except Exception as e:
            return json.dumps({
                "error": f"Failed to parse AI Language Code: {str(e)}",
                "code": code,
                "suggestion": "Verify code format matches: /TN/[codes]/VL[num]/SC[num]/..."
            }, indent=2)
    
    def _parse_code(self, code: str) -> Dict[str, Any]:
        """Parse the AI Language Code string into structured parameters."""
        parsed = {}
        
        # Extract Tone (/TN/...)
        tone_match = re.search(r'/TN/([^/]+)', code)
        if tone_match:
            parsed['tone'] = self._parse_tone(tone_match.group(1))
        
        # Extract Vocabulary Level (/VL[number])
        vl_match = re.search(r'/VL(\d+)', code)
        if vl_match:
            parsed['vocabulary_level'] = int(vl_match.group(1))
        
        # Extract Sentence Complexity (/SC[number])
        sc_match = re.search(r'/SC(\d+)', code)
        if sc_match:
            parsed['sentence_complexity'] = int(sc_match.group(1))
        
        # Extract Figurative Language (/FL[number])
        fl_match = re.search(r'/FL(\d+)', code)
        if fl_match:
            parsed['figurative_language'] = int(fl_match.group(1))
        
        # Extract Language Formality (/LF[number])
        lf_match = re.search(r'/LF(\d+)', code)
        if lf_match:
            parsed['language_formality'] = int(lf_match.group(1))
        
        # Extract Level of Detail (/LD[number])
        ld_match = re.search(r'/LD(\d+)', code)
        if ld_match:
            parsed['level_of_detail'] = int(ld_match.group(1))
        
        # Extract Verb Strength (/VS[number])
        vs_match = re.search(r'/VS(\d+)', code)
        if vs_match:
            parsed['verb_strength'] = int(vs_match.group(1))
        
        # Extract Subject Expertise (/SE[number])
        se_match = re.search(r'/SE(\d+)', code)
        if se_match:
            parsed['subject_expertise'] = int(se_match.group(1))
        
        # Extract Audience (/AU-[text])
        au_match = re.search(r'/AU-([^/]+)', code)
        if au_match:
            parsed['audience_specification'] = au_match.group(1)
        
        return parsed
    
    def _parse_tone(self, tone_str: str) -> List[Dict[str, Any]]:
        """Parse tone codes with intensity levels."""
        tones = []
        # Split by comma for multiple tones: A3,P4,EMP2
        tone_parts = tone_str.split(',')
        
        for part in tone_parts:
            # Match pattern like "A3" or "EMP2"
            match = re.match(r'([A-Z]+)(\d+)', part.strip())
            if match:
                code = match.group(1)
                intensity = int(match.group(2))
                
                tone_name = self.TONE_CODES.get(code, f"Unknown ({code})")
                tones.append({
                    "code": code,
                    "name": tone_name,
                    "intensity": intensity,
                    "description": self._get_tone_description(code, intensity)
                })
        
        return tones
    
    def _get_tone_description(self, code: str, intensity: int) -> str:
        """Generate description for tone based on code and intensity."""
        tone_name = self.TONE_CODES.get(code, "Unknown")
        
        intensity_desc = {
            1: "subtle hint",
            2: "gentle presence",
            3: "moderate emphasis",
            4: "strong emphasis",
            5: "dominant characteristic"
        }.get(intensity, "moderate emphasis")
        
        return f"{tone_name} tone with {intensity_desc}"
    
    def _generate_guidelines(self, parsed: Dict[str, Any]) -> Dict[str, Any]:
        """Generate detailed writing guidelines from parsed parameters."""
        guidelines = {}
        
        # Tone Guidelines
        if 'tone' in parsed:
            tone_guidelines = []
            for tone in parsed['tone']:
                tone_guidelines.append(self._get_tone_guidelines(tone))
            guidelines['tone'] = {
                "layers": tone_guidelines,
                "application": "Layer these tones with primary tone dominating, secondary supporting, and tertiary as accent."
            }
        
        # Vocabulary Level Guidelines
        if 'vocabulary_level' in parsed:
            vl = parsed['vocabulary_level']
            guidelines['vocabulary'] = self._get_vocabulary_guidelines(vl)
        
        # Sentence Complexity Guidelines
        if 'sentence_complexity' in parsed:
            sc = parsed['sentence_complexity']
            guidelines['sentence_structure'] = self._get_sentence_complexity_guidelines(sc)
        
        # Figurative Language Guidelines
        if 'figurative_language' in parsed:
            fl = parsed['figurative_language']
            guidelines['figurative_language'] = self._get_figurative_language_guidelines(fl)
        
        # Language Formality Guidelines
        if 'language_formality' in parsed:
            lf = parsed['language_formality']
            guidelines['formality'] = self._get_formality_guidelines(lf)
        
        # Level of Detail Guidelines
        if 'level_of_detail' in parsed:
            ld = parsed['level_of_detail']
            guidelines['detail_level'] = self._get_detail_guidelines(ld)
        
        # Verb Strength Guidelines
        if 'verb_strength' in parsed:
            vs = parsed['verb_strength']
            guidelines['verb_usage'] = self._get_verb_strength_guidelines(vs)
        
        # Subject Expertise Guidelines
        if 'subject_expertise' in parsed:
            se = parsed['subject_expertise']
            guidelines['expertise_level'] = self._get_expertise_guidelines(se)
        
        return guidelines
    
    def _get_tone_guidelines(self, tone: Dict[str, Any]) -> Dict[str, Any]:
        """Generate specific guidelines for a tone."""
        tone_strategies = {
            'Authoritative': {
                1: "Occasional confident statements with data backing",
                2: "Regular use of expert language and definitive statements",
                3: "Strong expertise demonstrations, cite studies and research",
                4: "Dominant expert voice, command of subject matter clear",
                5: "Absolute authority, speak as the definitive source"
            },
            'Professional': {
                1: "Polished language, minimal casual expressions",
                2: "Business-appropriate throughout, avoid slang",
                3: "Corporate communication standards, formal structure",
                4: "High-level executive communication style",
                5: "C-suite level gravitas and polish"
            },
            'Empathetic': {
                1: "Acknowledge reader's perspective occasionally",
                2: "Regular recognition of challenges and concerns",
                3: "Demonstrate understanding of pain points consistently",
                4: "Deep emotional connection, validate feelings",
                5: "Profound empathy, reader feels truly understood"
            },
            'Friendly': {
                1: "Warm word choices, welcoming tone",
                2: "Conversational elements, approachable language",
                3: "Like talking to a knowledgeable friend",
                4: "Very warm and inviting, personal connection",
                5: "Best friend energy, deeply relatable"
            },
            'Helpful': {
                1: "Provide useful information clearly",
                2: "Focus on actionable guidance",
                3: "Step-by-step support, problem-solving focus",
                4: "Comprehensive assistance, anticipate needs",
                5: "Ultimate resource, answer every possible question"
            }
        }
        
        strategy = tone_strategies.get(tone['name'], {}).get(
            tone['intensity'],
            f"Apply {tone['name'].lower()} tone at level {tone['intensity']}"
        )
        
        return {
            "tone": tone['name'],
            "intensity": tone['intensity'],
            "strategy": strategy
        }
    
    def _get_vocabulary_guidelines(self, level: int) -> Dict[str, Any]:
        """Generate vocabulary usage guidelines."""
        vocab_specs = {
            1: {
                "description": "Very basic, everyday language",
                "common_words": "90-100%",
                "uncommon_words": "0-10%",
                "advanced_words": "0%",
                "example": "help, make, good, easy, people, work"
            },
            2: {
                "description": "Simple but professional",
                "common_words": "80%",
                "uncommon_words": "15%",
                "advanced_words": "5%",
                "example": "implement, facilitate, enhance, establish"
            },
            3: {
                "description": "Accessible professional vocabulary",
                "common_words": "70%",
                "uncommon_words": "20%",
                "advanced_words": "10%",
                "example": "optimize, leverage, strategic, comprehensive"
            },
            4: {
                "description": "Advanced professional vocabulary",
                "common_words": "60%",
                "uncommon_words": "25%",
                "advanced_words": "15%",
                "example": "synthesize, paradigm, methodology, proprietary"
            },
            5: {
                "description": "Sophisticated business vocabulary",
                "common_words": "50%",
                "uncommon_words": "30%",
                "advanced_words": "20%",
                "example": "nomenclature, synergistic, multifaceted, holistic"
            },
            6: {
                "description": "Specialized professional language",
                "common_words": "40%",
                "uncommon_words": "35%",
                "advanced_words": "25%",
                "example": "actualize, paradigmatic, architectonic, systematic"
            },
            7: {
                "description": "Industry-specific technical terms",
                "common_words": "30%",
                "uncommon_words": "40%",
                "advanced_words": "30%",
                "example": "Domain-specific jargon, technical terminology"
            },
            8: {
                "description": "Highly specialized vocabulary",
                "common_words": "20%",
                "uncommon_words": "40%",
                "advanced_words": "40%",
                "example": "Advanced technical language, field-specific terms"
            },
            9: {
                "description": "Academic/expert-level language",
                "common_words": "10%",
                "uncommon_words": "40%",
                "advanced_words": "50%",
                "example": "Scholarly terminology, research-specific language"
            },
            10: {
                "description": "Highly technical/academic",
                "common_words": "0-5%",
                "uncommon_words": "45%",
                "advanced_words": "50-55%",
                "example": "Research papers, highly specialized publications"
            }
        }
        
        return vocab_specs.get(level, vocab_specs[5])
    
    def _get_sentence_complexity_guidelines(self, level: int) -> Dict[str, Any]:
        """Generate sentence structure guidelines."""
        complexity_specs = {
            1: {
                "description": "Very simple sentences",
                "simple": "60-80%",
                "compound": "10-20%",
                "complex": "10-20%",
                "compound_complex": "0%",
                "avg_length": "10-15 words",
                "example": "We help businesses grow. Our solutions are effective."
            },
            2: {
                "description": "Mostly simple with some variation",
                "simple": "50-60%",
                "compound": "20-25%",
                "complex": "15-20%",
                "compound_complex": "0-5%",
                "avg_length": "12-18 words",
                "example": "We help businesses grow, and our solutions are effective."
            },
            3: {
                "description": "Balanced mix of structures",
                "simple": "40-50%",
                "compound": "30%",
                "complex": "20-30%",
                "compound_complex": "0-5%",
                "avg_length": "15-20 words",
                "example": "We help businesses grow through solutions that are effective."
            },
            4: {
                "description": "More complex structures",
                "simple": "25-35%",
                "compound": "35%",
                "complex": "30-35%",
                "compound_complex": "5%",
                "avg_length": "18-25 words",
                "example": "While many businesses struggle, we provide solutions that help them grow effectively."
            },
            5: {
                "description": "Sophisticated, varied structures",
                "simple": "5%",
                "compound": "50%",
                "complex": "35%",
                "compound_complex": "10%",
                "avg_length": "20-30 words",
                "example": "Although challenges persist, our comprehensive solutions, which have been tested extensively, help businesses grow."
            }
        }
        
        return complexity_specs.get(level, complexity_specs[3])
    
    def _get_figurative_language_guidelines(self, level: int) -> Dict[str, Any]:
        """Generate figurative language usage guidelines."""
        fl_specs = {
            1: {
                "description": "Minimal figurative language",
                "frequency": "0-5% of sentences",
                "usage": "Rare and only when highly effective",
                "types": "Simple similes only"
            },
            2: {
                "description": "Occasional figurative language",
                "frequency": "5-15% of sentences",
                "usage": "Strategic use for emphasis",
                "types": "Similes and basic metaphors"
            },
            3: {
                "description": "Moderate figurative language",
                "frequency": "15-25% of sentences",
                "usage": "Regular enhancement of explanations",
                "types": "Metaphors, similes, and analogies"
            },
            4: {
                "description": "Frequent figurative language",
                "frequency": "25-40% of sentences",
                "usage": "Adds depth and imagery regularly",
                "types": "Extended metaphors and elaborate analogies"
            },
            5: {
                "description": "Rich, imaginative language",
                "frequency": "40-60% of sentences",
                "usage": "Integral to style with layered expressions",
                "types": "Complex metaphors, personification, vivid imagery"
            }
        }
        
        return fl_specs.get(level, fl_specs[2])
    
    def _get_formality_guidelines(self, level: int) -> Dict[str, Any]:
        """Generate language formality guidelines."""
        formality_specs = {
            1: {
                "description": "Highly informal/colloquial",
                "characteristics": "Conversational, casual, slang acceptable",
                "contractions": "Frequent",
                "personal_pronouns": "Very common (you, we, I)",
                "example": "Hey, let's dive into this!"
            },
            2: {
                "description": "Informal but professional",
                "characteristics": "Friendly business communication",
                "contractions": "Common",
                "personal_pronouns": "Common (you, we)",
                "example": "Let's explore how we can help you."
            },
            3: {
                "description": "Balanced professional",
                "characteristics": "Professional but approachable",
                "contractions": "Occasional",
                "personal_pronouns": "Moderate use",
                "example": "We will explore how to address this challenge."
            },
            4: {
                "description": "Formal business",
                "characteristics": "Corporate communication standards",
                "contractions": "Rare",
                "personal_pronouns": "Limited use",
                "example": "This analysis will explore the challenges."
            },
            5: {
                "description": "Highly formal/academic",
                "characteristics": "Academic or legal precision",
                "contractions": "Never",
                "personal_pronouns": "Minimal or none",
                "example": "This document presents an analysis of the challenges."
            }
        }
        
        return formality_specs.get(level, formality_specs[3])
    
    def _get_detail_guidelines(self, level: int) -> Dict[str, Any]:
        """Generate level of detail guidelines."""
        detail_specs = {
            1: {
                "description": "Very concise overview",
                "overview": "90-100%",
                "detail": "0-10%",
                "approach": "Essential points only, minimal elaboration"
            },
            2: {
                "description": "Brief with key details",
                "overview": "75-85%",
                "detail": "15-25%",
                "approach": "Main points with surface-level details"
            },
            3: {
                "description": "Balanced coverage",
                "overview": "50-60%",
                "detail": "40-50%",
                "approach": "Key points with moderate depth and examples"
            },
            4: {
                "description": "Detailed analysis",
                "overview": "25-35%",
                "detail": "65-75%",
                "approach": "Comprehensive with detailed examples and context"
            },
            5: {
                "description": "Exhaustive detail",
                "overview": "0-10%",
                "detail": "90-100%",
                "approach": "Every facet covered with examples and citations"
            }
        }
        
        return detail_specs.get(level, detail_specs[3])
    
    def _get_verb_strength_guidelines(self, level: int) -> Dict[str, Any]:
        """Generate verb strength guidelines."""
        if level <= 3:
            desc = "Basic, common verbs"
            examples_weak = "is, has, gets, does, makes"
            examples_strong = "helps, creates, provides, shows"
        elif level <= 5:
            desc = "Moderate action verbs"
            examples_weak = "uses, works, gives"
            examples_strong = "implements, facilitates, delivers, establishes"
        elif level <= 7:
            desc = "Strong action verbs"
            examples_weak = "changes, improves"
            examples_strong = "transforms, optimizes, revolutionizes, accelerates"
        else:
            desc = "Dynamic, impactful verbs"
            examples_weak = "affects, influences"
            examples_strong = "catalyzes, propels, ignites, amplifies, decimates"
        
        return {
            "level": level,
            "description": desc,
            "weak_verbs_to_avoid": examples_weak,
            "strong_verbs_to_use": examples_strong,
            "guideline": f"Use verbs at strength level {level}/10"
        }
    
    def _get_expertise_guidelines(self, level: int) -> Dict[str, Any]:
        """Generate subject expertise guidelines."""
        expertise_specs = {
            1: {
                "description": "General population knowledge",
                "depth": "Basic understanding, minimal research",
                "assumptions": "No prior knowledge assumed",
                "language": "Explain everything simply"
            },
            2: {
                "description": "Informed consumer level",
                "depth": "Surface-level industry knowledge",
                "assumptions": "Basic familiarity with topic",
                "language": "Some terminology acceptable with context"
            },
            3: {
                "description": "Professional familiarity",
                "depth": "Working knowledge of concepts",
                "assumptions": "Audience has relevant experience",
                "language": "Industry terminology used naturally"
            },
            4: {
                "description": "Subject matter competence",
                "depth": "Significant expertise demonstrated",
                "assumptions": "Advanced understanding expected",
                "language": "Technical language, nuanced discussions"
            },
            5: {
                "description": "Expert-level insights",
                "depth": "Decades of experience evident",
                "assumptions": "Expert-to-expert communication",
                "language": "Cutting-edge concepts, research-level"
            }
        }
        
        return expertise_specs.get(level, expertise_specs[3])
    
    def _generate_summary(self, parsed: Dict[str, Any]) -> str:
        """Generate a human-readable summary of the voice parameters."""
        summary_parts = []
        
        if 'tone' in parsed:
            tones = [f"{t['name']} (Level {t['intensity']})" for t in parsed['tone']]
            summary_parts.append(f"Tone: {', '.join(tones)}")
        
        if 'vocabulary_level' in parsed:
            vl = parsed['vocabulary_level']
            summary_parts.append(f"Vocabulary: Level {vl}/10")
        
        if 'sentence_complexity' in parsed:
            sc = parsed['sentence_complexity']
            summary_parts.append(f"Sentence Complexity: Level {sc}/5")
        
        if 'figurative_language' in parsed:
            fl = parsed['figurative_language']
            summary_parts.append(f"Figurative Language: Level {fl}/5")
        
        if 'language_formality' in parsed:
            lf = parsed['language_formality']
            summary_parts.append(f"Formality: Level {lf}/5")
        
        return " | ".join(summary_parts)


# =============================================================================
# TOOL INITIALIZATION
# =============================================================================

# Create tool instance for import
ai_language_code_parser = AILanguageCodeParser()


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def parse_ai_language_code(code: str) -> Dict[str, Any]:
    """
    Utility function to parse AI Language Code without using the tool interface.
    
    Args:
        code: AI Language Code string
    
    Returns:
        Dictionary with parsed parameters
    """
    parser = AILanguageCodeParser()
    result_json = parser._run(code)
    return json.loads(result_json)


def validate_ai_language_code(code: str) -> bool:
    """
    Validate if an AI Language Code string is properly formatted.
    
    Args:
        code: AI Language Code string to validate
    
    Returns:
        True if valid, False otherwise
    """
    try:
        # Check for basic structure
        if not code.startswith('/'):
            return False
        
        # Attempt to parse
        result = parse_ai_language_code(code)
        
        # Check if parsing was successful (no error in result)
        return 'error' not in result
    
    except Exception:
        return False


def generate_example_code(
    tone_primary: str = 'P',
    tone_intensity_primary: int = 3,
    vocabulary_level: int = 4,
    sentence_complexity: int = 3,
    figurative_language: int = 2,
    language_formality: int = 3
) -> str:
    """
    Generate a valid AI Language Code from parameters.
    
    Args:
        tone_primary: Primary tone code (e.g., 'P' for Professional)
        tone_intensity_primary: Intensity level 1-5
        vocabulary_level: Vocabulary sophistication 1-10
        sentence_complexity: Sentence structure complexity 1-5
        figurative_language: Figurative language frequency 1-5
        language_formality: Formality level 1-5
    
    Returns:
        Valid AI Language Code string
    """
    code_parts = [
        f"/TN/{tone_primary}{tone_intensity_primary}",
        f"/VL{vocabulary_level}",
        f"/SC{sentence_complexity}",
        f"/FL{figurative_language}",
        f"/LF{language_formality}"
    ]
    
    return ''.join(code_parts)


# =============================================================================
# EXAMPLE USAGE AND TESTING
# =============================================================================

if __name__ == "__main__":
    """
    Test the AI Language Code Parser with example codes.
    """
    
    print("=" * 80)
    print("AI LANGUAGE CODE PARSER - TEST EXAMPLES")
    print("=" * 80)
    
    # Example 1: Professional Blog Content
    print("\n" + "-" * 80)
    print("Example 1: Professional Blog Content")
    print("-" * 80)
    code1 = "/TN/A3,P4,EMP2/VL4/SC3/FL2/LF3/LD3/VS6"
    result1 = parse_ai_language_code(code1)
    print(f"\nCode: {code1}")
    print(f"\nSummary: {result1['summary']}")
    print("\nParsed Parameters:")
    print(json.dumps(result1['parsed_parameters'], indent=2))
    
    # Example 2: Technical Documentation
    print("\n" + "-" * 80)
    print("Example 2: Technical Documentation")
    print("-" * 80)
    code2 = "/TN/A4,P5/VL7/SC4/FL1/LF4/LD4/VS5"
    result2 = parse_ai_language_code(code2)
    print(f"\nCode: {code2}")
    print(f"\nSummary: {result2['summary']}")
    
    # Example 3: Casual Marketing Content
    print("\n" + "-" * 80)
    print("Example 3: Casual Marketing Content")
    print("-" * 80)
    code3 = "/TN/F4,ET3,H2/VL3/SC2/FL3/LF2/LD2/VS7"
    result3 = parse_ai_language_code(code3)
    print(f"\nCode: {code3}")
    print(f"\nSummary: {result3['summary']}")
    
    # Test code generation
    print("\n" + "-" * 80)
    print("Example 4: Generated Code")
    print("-" * 80)
    generated_code = generate_example_code(
        tone_primary='A',
        tone_intensity_primary=3,
        vocabulary_level=5,
        sentence_complexity=3,
        figurative_language=2,
        language_formality=3
    )
    print(f"\nGenerated Code: {generated_code}")
    print(f"Valid: {validate_ai_language_code(generated_code)}")
    
    print("\n" + "=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)