"""
IBM Bob - Input Validation & Sanitization
Comprehensive input validation to prevent injection attacks
"""

import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from bob.exceptions import InvalidQueryError


class QueryValidator:
    """Validates and sanitizes search queries and file paths"""

    # Maximum lengths
    MAX_QUERY_LENGTH = 500
    MAX_FILE_PATH_LENGTH = 1000
    MAX_REPO_ID_LENGTH = 100

    # Dangerous patterns
    SQL_INJECTION_PATTERNS = [
        r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|EXECUTE)\b)",
        r"(--|;|\/\*|\*\/)",
        r"(\bOR\b.*=.*)",
        r"(\bAND\b.*=.*)",
    ]

    SCRIPT_PATTERNS = [
        r"<script[^>]*>.*?</script>",
        r"javascript:",
        r"on\w+\s*=",
    ]

    PATH_TRAVERSAL_PATTERNS = [
        r"\.\./",
        r"\.\.",
        r"~",
        r"^/",
    ]

    @classmethod
    def validate_search_query(cls, query: str) -> str:
        """
        Validate and sanitize search queries.

        Args:
            query: Search query string

        Returns:
            Sanitized query string

        Raises:
            InvalidQueryError: If query is invalid
        """
        if not query or not query.strip():
            raise InvalidQueryError("Query cannot be empty")

        # Check length
        if len(query) > cls.MAX_QUERY_LENGTH:
            raise InvalidQueryError(
                f"Query too long. Maximum length: {cls.MAX_QUERY_LENGTH} characters"
            )

        # Check for SQL injection patterns
        for pattern in cls.SQL_INJECTION_PATTERNS:
            if re.search(pattern, query, re.IGNORECASE):
                raise InvalidQueryError("Query contains potentially dangerous SQL patterns")

        # Check for script injection
        for pattern in cls.SCRIPT_PATTERNS:
            if re.search(pattern, query, re.IGNORECASE):
                raise InvalidQueryError("Query contains potentially dangerous script patterns")

        # Sanitize: remove control characters
        sanitized = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", query)

        # Trim whitespace
        sanitized = sanitized.strip()

        return sanitized

    @classmethod
    def validate_file_path(cls, path: str) -> str:
        """
        Validate file paths to prevent directory traversal.

        Args:
            path: File path string

        Returns:
            Sanitized file path

        Raises:
            InvalidQueryError: If path is invalid
        """
        if not path or not path.strip():
            raise InvalidQueryError("File path cannot be empty")

        # Check length
        if len(path) > cls.MAX_FILE_PATH_LENGTH:
            raise InvalidQueryError(
                f"File path too long. Maximum length: {cls.MAX_FILE_PATH_LENGTH}"
            )

        # Check for path traversal patterns
        for pattern in cls.PATH_TRAVERSAL_PATTERNS:
            if re.search(pattern, path):
                raise InvalidQueryError("File path contains potentially dangerous patterns")

        # Must be relative path
        if Path(path).is_absolute():
            raise InvalidQueryError("File path must be relative")

        # Normalize path
        try:
            normalized = Path(path).as_posix()
        except Exception:
            raise InvalidQueryError("Invalid file path format")

        # Ensure normalized path doesn't escape
        if normalized.startswith(".."):
            raise InvalidQueryError("File path cannot traverse parent directories")

        return normalized

    @classmethod
    def validate_repo_id(cls, repo_id: str) -> str:
        """
        Validate repository ID format.

        Args:
            repo_id: Repository identifier (owner/repo or UUID)

        Returns:
            Validated repo ID

        Raises:
            InvalidQueryError: If repo ID is invalid
        """
        if not repo_id or not repo_id.strip():
            raise InvalidQueryError("Repository ID cannot be empty")

        # Check length
        if len(repo_id) > cls.MAX_REPO_ID_LENGTH:
            raise InvalidQueryError(
                f"Repository ID too long. Maximum length: {cls.MAX_REPO_ID_LENGTH}"
            )

        # Try to parse as UUID first
        try:
            UUID(repo_id)
            return repo_id
        except ValueError:
            pass

        # Otherwise, validate as owner/repo format
        if "/" in repo_id:
            parts = repo_id.split("/")
            if len(parts) != 2:
                raise InvalidQueryError(
                    "Repository ID must be in format 'owner/repo' or valid UUID"
                )

            owner, repo = parts

            # Validate owner and repo names
            if not cls._is_valid_identifier(owner):
                raise InvalidQueryError("Invalid repository owner name")

            if not cls._is_valid_identifier(repo):
                raise InvalidQueryError("Invalid repository name")

            return repo_id

        raise InvalidQueryError("Repository ID must be in format 'owner/repo' or valid UUID")

    @classmethod
    def _is_valid_identifier(cls, identifier: str) -> bool:
        """Check if identifier contains only allowed characters"""
        # Allow alphanumeric, hyphens, underscores, dots
        pattern = r"^[a-zA-Z0-9._-]+$"
        return bool(re.match(pattern, identifier))


class RequestValidator:
    """Validates API request parameters"""

    @staticmethod
    def validate_pagination(page: int, page_size: int) -> Tuple[int, int]:
        """
        Validate pagination parameters.

        Args:
            page: Page number (1-indexed)
            page_size: Items per page

        Returns:
            Tuple of (validated_page, validated_page_size)

        Raises:
            InvalidQueryError: If parameters are invalid
        """
        # Validate page
        if page < 1:
            raise InvalidQueryError("Page number must be >= 1")

        if page > 10000:
            raise InvalidQueryError("Page number too large (max: 10000)")

        # Validate page_size
        if page_size < 1:
            raise InvalidQueryError("Page size must be >= 1")

        if page_size > 100:
            raise InvalidQueryError("Page size too large (max: 100)")

        return page, page_size

    @staticmethod
    def validate_batch_size(size: int, max_size: int = 50) -> int:
        """
        Validate batch request sizes.

        Args:
            size: Batch size
            max_size: Maximum allowed batch size

        Returns:
            Validated batch size

        Raises:
            InvalidQueryError: If size is invalid
        """
        if size < 1:
            raise InvalidQueryError("Batch size must be >= 1")

        if size > max_size:
            raise InvalidQueryError(f"Batch size too large (max: {max_size})")

        return size

    @staticmethod
    def validate_hops(hops: int, max_hops: int = 10) -> int:
        """
        Validate graph traversal hops.

        Args:
            hops: Number of hops
            max_hops: Maximum allowed hops

        Returns:
            Validated hops

        Raises:
            InvalidQueryError: If hops is invalid
        """
        if hops < 1:
            raise InvalidQueryError("Hops must be >= 1")

        if hops > max_hops:
            raise InvalidQueryError(f"Hops too large (max: {max_hops})")

        return hops

    @staticmethod
    def validate_k(k: int, max_k: int = 50) -> int:
        """
        Validate search result count (k).

        Args:
            k: Number of results
            max_k: Maximum allowed results

        Returns:
            Validated k

        Raises:
            InvalidQueryError: If k is invalid
        """
        if k < 1:
            raise InvalidQueryError("k must be >= 1")

        if k > max_k:
            raise InvalidQueryError(f"k too large (max: {max_k})")

        return k

    @staticmethod
    def validate_direction(direction: str) -> str:
        """
        Validate graph traversal direction.

        Args:
            direction: Direction string

        Returns:
            Validated direction

        Raises:
            InvalidQueryError: If direction is invalid
        """
        valid_directions = {"upstream", "downstream", "both"}

        if direction not in valid_directions:
            raise InvalidQueryError(
                f"Invalid direction. Must be one of: {', '.join(valid_directions)}"
            )

        return direction

    @staticmethod
    def validate_commit_sha(sha: str) -> str:
        """
        Validate git commit SHA.

        Args:
            sha: Commit SHA (short or full)

        Returns:
            Validated SHA

        Raises:
            InvalidQueryError: If SHA is invalid
        """
        if not sha or not sha.strip():
            raise InvalidQueryError("Commit SHA cannot be empty")

        # Remove whitespace
        sha = sha.strip()

        # Check format (hex characters only)
        if not re.match(r"^[0-9a-f]+$", sha, re.IGNORECASE):
            raise InvalidQueryError("Commit SHA must contain only hexadecimal characters")

        # Check length (short: 7-40, full: 40)
        if len(sha) < 7 or len(sha) > 40:
            raise InvalidQueryError("Commit SHA must be 7-40 characters")

        return sha.lower()


class SearchRequestModel(BaseModel):
    """Validated search request model"""

    repo_id: str = Field(..., description="Repository UUID")
    query: str = Field(..., min_length=1, max_length=500)
    k: int = Field(default=10, ge=1, le=50)
    filter: Optional[Dict[str, str]] = None

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        return QueryValidator.validate_search_query(v)

    @field_validator("repo_id")
    @classmethod
    def validate_repo_id(cls, v: str) -> str:
        return QueryValidator.validate_repo_id(v)


class FileRequestModel(BaseModel):
    """Validated file request model"""

    repo_id: str = Field(..., description="Repository UUID")
    file_path: str = Field(..., min_length=1, max_length=1000)

    @field_validator("file_path")
    @classmethod
    def validate_file_path(cls, v: str) -> str:
        return QueryValidator.validate_file_path(v)

    @field_validator("repo_id")
    @classmethod
    def validate_repo_id(cls, v: str) -> str:
        return QueryValidator.validate_repo_id(v)


class DependencyGraphRequestModel(BaseModel):
    """Validated dependency graph request model"""

    repo_id: str = Field(..., description="Repository UUID")
    file_path: str = Field(..., min_length=1, max_length=1000)
    hops: int = Field(default=3, ge=1, le=10)
    direction: str = Field(default="both", pattern="^(upstream|downstream|both)$")

    @field_validator("file_path")
    @classmethod
    def validate_file_path(cls, v: str) -> str:
        return QueryValidator.validate_file_path(v)

    @field_validator("repo_id")
    @classmethod
    def validate_repo_id(cls, v: str) -> str:
        return QueryValidator.validate_repo_id(v)


class BlastRadiusRequestModel(BaseModel):
    """Validated blast radius request model"""

    repo_id: str = Field(..., description="Repository UUID")
    files: list[str] = Field(..., min_length=1, max_length=100)

    @field_validator("files")
    @classmethod
    def validate_files(cls, v: list[str]) -> list[str]:
        return [QueryValidator.validate_file_path(f) for f in v]

    @field_validator("repo_id")
    @classmethod
    def validate_repo_id(cls, v: str) -> str:
        return QueryValidator.validate_repo_id(v)


def sanitize_error_message(message: str) -> str:
    """
    Sanitize error messages to prevent information leakage.

    Args:
        message: Error message

    Returns:
        Sanitized message
    """
    # Remove file paths
    message = re.sub(r"/[\w/.-]+", "[PATH]", message)

    # Remove IP addresses
    message = re.sub(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", "[IP]", message)

    # Remove potential secrets (long alphanumeric strings)
    message = re.sub(r"\b[a-zA-Z0-9]{32,}\b", "[REDACTED]", message)

    return message


# Made with Bob
