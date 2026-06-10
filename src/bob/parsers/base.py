"""
IBM Bob - Language Parser Base Class
Abstract base class for language-specific parsers using Tree-sitter
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class SymbolType(Enum):
    """Types of code symbols that can be extracted"""

    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    INTERFACE = "interface"
    ENUM = "enum"
    CONSTANT = "constant"
    VARIABLE = "variable"
    IMPORT = "import"
    EXPORT = "export"


@dataclass
class CodeSymbol:
    """Represents a parsed code symbol (class, function, etc.)"""

    name: str
    symbol_type: SymbolType
    file_path: str
    start_line: int
    end_line: int
    start_byte: int
    end_byte: int
    signature: str | None = None
    docstring: str | None = None
    parent: str | None = None  # Parent class/module name
    modifiers: list[str] | None = None  # public, private, static, async, etc.
    parameters: list[str] | None = None  # Function/method parameters
    return_type: str | None = None
    body: str | None = None  # Full body content


@dataclass
class ImportStatement:
    """Represents an import/require statement"""

    module: str  # Module being imported
    imported_names: list[str]  # Specific names imported (empty for wildcard)
    alias: str | None = None  # Import alias
    is_relative: bool = False  # Relative vs absolute import
    file_path: str = ""
    line_number: int = 0


@dataclass
class ParseResult:
    """Result of parsing a source file"""

    file_path: str
    language: str
    symbols: list[CodeSymbol]
    imports: list[ImportStatement]
    exports: list[str]  # Exported symbol names
    total_lines: int
    code_lines: int  # Non-comment, non-blank lines
    comment_lines: int
    parse_errors: list[str]  # Non-fatal parse errors
    success: bool = True


class LanguageParser(ABC):
    """
    Abstract base class for language-specific parsers.

    Each language parser must:
    1. Use Tree-sitter for AST extraction
    2. Extract classes, functions, imports, line ranges, signatures
    3. Handle binary file detection and skipping
    4. Provide graceful error handling for parse failures
    """

    def __init__(self) -> None:
        """Initialize the parser"""
        self._parser: Any | None = None
        self._language: Any | None = None

    @property
    @abstractmethod
    def language_name(self) -> str:
        """Return the language name (e.g., 'python', 'typescript')"""
        pass

    @property
    @abstractmethod
    def file_extensions(self) -> list[str]:
        """Return supported file extensions (e.g., ['.py', '.pyi'])"""
        pass

    @abstractmethod
    def _setup_parser(self) -> None:
        """
        Initialize Tree-sitter parser for this language.
        Must set self._parser and self._language.
        """
        pass

    @abstractmethod
    def _extract_symbols(self, tree: Any, source_code: bytes) -> list[CodeSymbol]:
        """
        Extract code symbols from AST.

        Args:
            tree: Tree-sitter parse tree
            source_code: Source code as bytes

        Returns:
            List of extracted symbols
        """
        pass

    @abstractmethod
    def _extract_imports(self, tree: Any, source_code: bytes) -> list[ImportStatement]:
        """
        Extract import statements from AST.

        Args:
            tree: Tree-sitter parse tree
            source_code: Source code as bytes

        Returns:
            List of import statements
        """
        pass

    def can_parse(self, file_path: Path) -> bool:
        """
        Check if this parser can handle the given file.

        Args:
            file_path: Path to file

        Returns:
            True if file extension is supported
        """
        return file_path.suffix.lower() in self.file_extensions

    def is_binary_file(self, file_path: Path) -> bool:
        """
        Check if file is binary (should be skipped).

        Args:
            file_path: Path to file

        Returns:
            True if file appears to be binary
        """
        try:
            with open(file_path, "rb") as f:
                chunk = f.read(8192)
                # Check for null bytes (common in binary files)
                if b"\x00" in chunk:
                    return True
                # Try to decode as UTF-8
                try:
                    chunk.decode("utf-8")
                    return False
                except UnicodeDecodeError:
                    return True
        except Exception as e:
            logger.warning(f"Error checking if file is binary: {e}")
            return True

    def parse_file(self, file_path: Path) -> ParseResult:
        """
        Parse a source file and extract all relevant information.

        Args:
            file_path: Path to source file

        Returns:
            ParseResult with extracted information

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file is binary or unsupported
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if not self.can_parse(file_path):
            raise ValueError(
                f"File extension {file_path.suffix} not supported by {self.language_name} parser"
            )

        if self.is_binary_file(file_path):
            raise ValueError(f"File is binary: {file_path}")

        # Initialize parser if needed
        if self._parser is None:
            self._setup_parser()

        try:
            # Read source code
            with open(file_path, "rb") as f:
                source_code = f.read()

            # Parse with Tree-sitter
            tree = self._parser.parse(source_code)

            # Check for parse errors
            parse_errors = []
            if tree.root_node.has_error:
                parse_errors.append("Tree-sitter detected syntax errors")
                logger.warning(f"Parse errors in {file_path}")

            # Extract symbols and imports
            symbols = self._extract_symbols(tree, source_code)
            imports = self._extract_imports(tree, source_code)

            # Extract exports (language-specific, default to empty)
            exports = self._extract_exports(tree, source_code)

            # Count lines
            source_text = source_code.decode("utf-8")
            lines = source_text.split("\n")
            total_lines = len(lines)
            code_lines, comment_lines = self._count_lines(source_text)

            return ParseResult(
                file_path=str(file_path),
                language=self.language_name,
                symbols=symbols,
                imports=imports,
                exports=exports,
                total_lines=total_lines,
                code_lines=code_lines,
                comment_lines=comment_lines,
                parse_errors=parse_errors,
                success=len(parse_errors) == 0,
            )

        except Exception as e:
            logger.error(f"Failed to parse {file_path}: {e}", exc_info=True)
            return ParseResult(
                file_path=str(file_path),
                language=self.language_name,
                symbols=[],
                imports=[],
                exports=[],
                total_lines=0,
                code_lines=0,
                comment_lines=0,
                parse_errors=[str(e)],
                success=False,
            )

    def _extract_exports(self, tree: Any, source_code: bytes) -> list[str]:
        """
        Extract exported symbols (default implementation).
        Override in language-specific parsers if needed.

        Args:
            tree: Tree-sitter parse tree
            source_code: Source code as bytes

        Returns:
            List of exported symbol names
        """
        return []

    def _count_lines(self, source_text: str) -> tuple[int, int]:
        """
        Count code lines and comment lines.

        Args:
            source_text: Source code as string

        Returns:
            Tuple of (code_lines, comment_lines)
        """
        lines = source_text.split("\n")
        code_lines = 0
        comment_lines = 0

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if self._is_comment_line(stripped):
                comment_lines += 1
            else:
                code_lines += 1

        return code_lines, comment_lines

    def _is_comment_line(self, line: str) -> bool:
        """
        Check if a line is a comment (language-specific).
        Override in subclasses for accurate detection.

        Args:
            line: Stripped line of code

        Returns:
            True if line is a comment
        """
        # Default implementation - override in subclasses
        return line.startswith("#") or line.startswith("//")

    def _get_node_text(self, node: Any, source_code: bytes) -> str:
        """
        Extract text content from a Tree-sitter node.

        Args:
            node: Tree-sitter node
            source_code: Source code as bytes

        Returns:
            Node text as string
        """
        return source_code[node.start_byte : node.end_byte].decode("utf-8")

    def _get_node_line_range(self, node: Any) -> tuple[int, int]:
        """
        Get line range for a Tree-sitter node.

        Args:
            node: Tree-sitter node

        Returns:
            Tuple of (start_line, end_line) (1-indexed)
        """
        return node.start_point[0] + 1, node.end_point[0] + 1

    def parse_directory(
        self,
        directory: Path,
        recursive: bool = True,
    ) -> list[ParseResult]:
        """
        Parse all supported files in a directory.

        Args:
            directory: Directory to parse
            recursive: Whether to recurse into subdirectories

        Returns:
            List of parse results
        """
        results = []

        if recursive:
            pattern = "**/*"
        else:
            pattern = "*"

        for file_path in directory.glob(pattern):
            if file_path.is_file() and self.can_parse(file_path):
                try:
                    result = self.parse_file(file_path)
                    results.append(result)
                except Exception as e:
                    logger.error(f"Failed to parse {file_path}: {e}")
                    # Add failed result
                    results.append(
                        ParseResult(
                            file_path=str(file_path),
                            language=self.language_name,
                            symbols=[],
                            imports=[],
                            exports=[],
                            total_lines=0,
                            code_lines=0,
                            comment_lines=0,
                            parse_errors=[str(e)],
                            success=False,
                        )
                    )

        return results


# Made with Bob
