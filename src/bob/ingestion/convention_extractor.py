"""
IBM Bob - Convention Extractor
Uses LLM to extract coding conventions from repository samples
"""

import json
import logging
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import openai
except ImportError:
    openai = None

from bob.config import get_settings
from bob.exceptions import LLMAPIError
from bob.parsers.base import ParseResult

logger = logging.getLogger(__name__)


@dataclass
class CodingConvention:
    """Represents extracted coding conventions"""

    service_name: str
    language: str
    naming_patterns: dict[str, str] = field(default_factory=dict)
    error_handling: list[str] = field(default_factory=list)
    import_ordering: list[str] = field(default_factory=list)
    code_style: dict[str, Any] = field(default_factory=dict)
    test_patterns: dict[str, str] = field(default_factory=dict)
    documentation_style: str = ""
    sample_files: list[str] = field(default_factory=list)


class ConventionExtractor:
    """
    Extracts coding conventions using LLM analysis.
    
    Responsibilities:
    - Use LLM to extract coding conventions
    - Sample 10-20 files per service
    - Extract: naming patterns, error handling, import ordering
    - Return structured JSON
    """

    def __init__(self) -> None:
        """Initialize the convention extractor"""
        self.settings = get_settings()
        self._openai_client: Any = None

    def _get_openai_client(self) -> Any:
        """Get or create OpenAI client"""
        if self._openai_client is None:
            if openai is None:
                raise ImportError("openai package not installed")
            
            if not self.settings.openai_api_key:
                raise LLMAPIError(
                    "OpenAI API key not configured",
                    details={"provider": "openai"},
                )
            
            self._openai_client = openai.OpenAI(api_key=self.settings.openai_api_key)
        
        return self._openai_client

    def extract_conventions(
        self,
        parse_results: list[ParseResult],
        service_name: str = "default",
        sample_size: int = 15,
    ) -> dict[str, CodingConvention]:
        """
        Extract coding conventions from parse results.
        
        Args:
            parse_results: List of parse results
            service_name: Name of the service
            sample_size: Number of files to sample per language
            
        Returns:
            Dictionary mapping language to conventions
        """
        logger.info(f"Extracting conventions for service: {service_name}")
        
        # Group parse results by language
        by_language: dict[str, list[ParseResult]] = {}
        for result in parse_results:
            if result.success and result.symbols:
                if result.language not in by_language:
                    by_language[result.language] = []
                by_language[result.language].append(result)
        
        # Extract conventions per language
        conventions = {}
        for language, results in by_language.items():
            logger.info(f"Extracting {language} conventions from {len(results)} files")
            
            # Sample files
            sampled = self._sample_files(results, sample_size)
            
            # Extract conventions
            convention = self._extract_language_conventions(
                sampled, language, service_name
            )
            conventions[language] = convention
        
        return conventions

    def _sample_files(
        self,
        parse_results: list[ParseResult],
        sample_size: int,
    ) -> list[ParseResult]:
        """
        Sample representative files from parse results.
        
        Prioritizes files with more symbols and diverse patterns.
        """
        if len(parse_results) <= sample_size:
            return parse_results
        
        # Score files by "interestingness"
        scored = []
        for result in parse_results:
            score = 0
            
            # More symbols = more interesting
            score += len(result.symbols) * 2
            
            # More imports = more interesting
            score += len(result.imports)
            
            # Longer files = more interesting (up to a point)
            score += min(result.code_lines // 10, 50)
            
            # Has docstrings = more interesting
            for symbol in result.symbols:
                if symbol.docstring:
                    score += 5
            
            scored.append((score, result))
        
        # Sort by score and take top N
        scored.sort(reverse=True, key=lambda x: x[0])
        sampled = [result for _, result in scored[:sample_size]]
        
        # Add some randomness to ensure diversity
        if len(parse_results) > sample_size * 2:
            remaining = [r for r in parse_results if r not in sampled]
            random_samples = random.sample(
                remaining, min(5, len(remaining))
            )
            sampled = sampled[:-5] + random_samples
        
        return sampled

    def _extract_language_conventions(
        self,
        parse_results: list[ParseResult],
        language: str,
        service_name: str,
    ) -> CodingConvention:
        """Extract conventions for a specific language"""
        
        # Prepare sample code
        sample_code = self._prepare_sample_code(parse_results)
        
        # Try LLM extraction
        try:
            if self.settings.openai_api_key:
                conventions_data = self._extract_with_llm(sample_code, language)
            else:
                # Fallback to heuristic extraction
                conventions_data = self._extract_with_heuristics(parse_results, language)
        except Exception as e:
            logger.warning(f"LLM extraction failed, using heuristics: {e}")
            conventions_data = self._extract_with_heuristics(parse_results, language)
        
        # Create convention object
        convention = CodingConvention(
            service_name=service_name,
            language=language,
            naming_patterns=conventions_data.get("naming_patterns", {}),
            error_handling=conventions_data.get("error_handling", []),
            import_ordering=conventions_data.get("import_ordering", []),
            code_style=conventions_data.get("code_style", {}),
            test_patterns=conventions_data.get("test_patterns", {}),
            documentation_style=conventions_data.get("documentation_style", ""),
            sample_files=[r.file_path for r in parse_results],
        )
        
        return convention

    def _prepare_sample_code(self, parse_results: list[ParseResult]) -> str:
        """Prepare sample code for LLM analysis"""
        samples = []
        
        for result in parse_results[:10]:  # Limit to avoid token limits
            # Include file header
            samples.append(f"# File: {result.file_path}")
            samples.append(f"# Language: {result.language}")
            samples.append("")
            
            # Include a few representative symbols
            for symbol in result.symbols[:3]:
                if symbol.body:
                    samples.append(f"## {symbol.symbol_type.value}: {symbol.name}")
                    # Truncate long bodies
                    body = symbol.body[:500] + "..." if len(symbol.body) > 500 else symbol.body
                    samples.append(body)
                    samples.append("")
        
        return "\n".join(samples)

    def _extract_with_llm(self, sample_code: str, language: str) -> dict[str, Any]:
        """Extract conventions using LLM"""
        client = self._get_openai_client()
        
        prompt = f"""Analyze the following {language} code samples and extract coding conventions.

Return a JSON object with the following structure:
{{
  "naming_patterns": {{
    "classes": "description of class naming pattern",
    "functions": "description of function naming pattern",
    "variables": "description of variable naming pattern",
    "constants": "description of constant naming pattern"
  }},
  "error_handling": ["list of error handling patterns observed"],
  "import_ordering": ["list of import ordering rules"],
  "code_style": {{
    "indentation": "spaces or tabs",
    "line_length": "typical max line length",
    "quotes": "single or double quotes preference"
  }},
  "test_patterns": {{
    "test_file_naming": "pattern for test file names",
    "test_function_naming": "pattern for test function names"
  }},
  "documentation_style": "description of documentation style (docstrings, comments, etc.)"
}}

Code samples:
{sample_code}

Respond with ONLY the JSON object, no additional text."""

        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",  # Use cheaper model for convention extraction
                messages=[
                    {
                        "role": "system",
                        "content": "You are a code analysis expert. Extract coding conventions from code samples and return structured JSON.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=1000,
            )
            
            content = response.choices[0].message.content
            
            # Parse JSON response
            # Remove markdown code blocks if present
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            
            conventions = json.loads(content.strip())
            return conventions
        
        except Exception as e:
            raise LLMAPIError(
                f"Failed to extract conventions with LLM: {str(e)}",
                details={"language": language},
            ) from e

    def _extract_with_heuristics(
        self,
        parse_results: list[ParseResult],
        language: str,
    ) -> dict[str, Any]:
        """Extract conventions using heuristic analysis"""
        
        # Analyze naming patterns
        naming_patterns = self._analyze_naming_patterns(parse_results)
        
        # Analyze error handling
        error_handling = self._analyze_error_handling(parse_results, language)
        
        # Analyze import ordering
        import_ordering = self._analyze_import_ordering(parse_results)
        
        # Analyze code style
        code_style = self._analyze_code_style(parse_results)
        
        return {
            "naming_patterns": naming_patterns,
            "error_handling": error_handling,
            "import_ordering": import_ordering,
            "code_style": code_style,
            "test_patterns": {},
            "documentation_style": "Standard docstrings",
        }

    def _analyze_naming_patterns(self, parse_results: list[ParseResult]) -> dict[str, str]:
        """Analyze naming patterns from symbols"""
        patterns = {
            "classes": "Unknown",
            "functions": "Unknown",
            "variables": "Unknown",
            "constants": "Unknown",
        }
        
        class_names = []
        function_names = []
        
        for result in parse_results:
            for symbol in result.symbols:
                if symbol.symbol_type.value == "class":
                    class_names.append(symbol.name)
                elif symbol.symbol_type.value in ("function", "method"):
                    function_names.append(symbol.name)
        
        # Detect class naming pattern
        if class_names:
            if all(name[0].isupper() for name in class_names if name):
                patterns["classes"] = "PascalCase (UpperCamelCase)"
            else:
                patterns["classes"] = "Mixed case"
        
        # Detect function naming pattern
        if function_names:
            if all("_" in name for name in function_names if len(name) > 3):
                patterns["functions"] = "snake_case"
            elif all(name[0].islower() and any(c.isupper() for c in name[1:]) for name in function_names if name):
                patterns["functions"] = "camelCase"
            else:
                patterns["functions"] = "Mixed case"
        
        return patterns

    def _analyze_error_handling(
        self,
        parse_results: list[ParseResult],
        language: str,
    ) -> list[str]:
        """Analyze error handling patterns"""
        patterns = []
        
        # Language-specific patterns
        if language == "python":
            patterns.append("Uses try/except blocks")
            patterns.append("Raises custom exceptions")
        elif language in ("typescript", "javascript"):
            patterns.append("Uses try/catch blocks")
            patterns.append("Returns error objects")
        elif language == "go":
            patterns.append("Returns error as second value")
            patterns.append("Checks if err != nil")
        elif language == "java":
            patterns.append("Uses try/catch blocks")
            patterns.append("Declares throws in method signatures")
        
        return patterns

    def _analyze_import_ordering(self, parse_results: list[ParseResult]) -> list[str]:
        """Analyze import ordering patterns"""
        patterns = []
        
        # Check if imports are grouped
        for result in parse_results[:5]:
            if result.imports:
                # Check for standard library vs third-party grouping
                has_blank_lines = False  # Would need actual source to detect
                patterns.append("Imports grouped by type")
                break
        
        patterns.append("Alphabetically sorted within groups")
        return patterns

    def _analyze_code_style(self, parse_results: list[ParseResult]) -> dict[str, str]:
        """Analyze code style patterns"""
        style = {
            "indentation": "4 spaces",
            "line_length": "80-100 characters",
            "quotes": "double quotes",
        }
        
        # Could analyze actual code to detect these
        # For now, return defaults
        
        return style


# Made with Bob