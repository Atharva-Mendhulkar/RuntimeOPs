"""
IBM Bob - Custom Exceptions
Centralized exception definitions for error handling
"""


class BobException(Exception):
    """Base exception for all Bob errors"""

    def __init__(self, message: str, details: dict | None = None) -> None:
        self.message = message
        self.details = details or {}
        super().__init__(self.message)


# Repository & Ingestion Exceptions
class RepositoryError(BobException):
    """Base exception for repository-related errors"""

    pass


class RepositoryNotFoundError(RepositoryError):
    """Repository not found or not accessible"""

    pass


class RepositoryCloneError(RepositoryError):
    """Failed to clone repository"""

    pass


class IndexingError(BobException):
    """Base exception for indexing errors"""

    pass


class IndexingTimeoutError(IndexingError):
    """Indexing operation timed out"""

    pass


class ParserError(BobException):
    """Base exception for parsing errors"""

    pass


class UnsupportedLanguageError(ParserError):
    """Language not supported by parser"""

    pass


# Graph & Database Exceptions
class GraphError(BobException):
    """Base exception for graph operations"""

    pass


class GraphConnectionError(GraphError):
    """Failed to connect to Neo4j"""

    pass


class GraphQueryError(GraphError):
    """Graph query execution failed"""

    pass


class VectorStoreError(BobException):
    """Base exception for vector store operations"""

    pass


class VectorStoreConnectionError(VectorStoreError):
    """Failed to connect to Weaviate"""

    pass


class EmbeddingError(BobException):
    """Failed to generate embeddings"""

    pass


# Query Exceptions
class QueryError(BobException):
    """Base exception for query operations"""

    pass


class QueryTimeoutError(QueryError):
    """Query execution timed out"""

    pass


class InvalidQueryError(QueryError):
    """Query parameters are invalid"""

    pass


# Security Exceptions
class SecurityError(BobException):
    """Base exception for security-related errors"""

    pass


class AuthenticationError(SecurityError):
    """Authentication failed"""

    pass


class AuthorizationError(SecurityError):
    """User not authorized for this operation"""

    pass


class InvalidTokenError(SecurityError):
    """JWT token is invalid or expired"""

    pass


class EncryptionError(SecurityError):
    """Encryption/decryption failed"""

    pass


# API Exceptions
class APIError(BobException):
    """Base exception for API errors"""

    pass


class RateLimitExceededError(APIError):
    """Rate limit exceeded"""

    pass


class ResourceNotFoundError(APIError):
    """Requested resource not found"""

    pass


# Configuration Exceptions
class ConfigurationError(BobException):
    """Configuration is invalid or missing"""

    pass


# External Service Exceptions
class ExternalServiceError(BobException):
    """External service (GitHub, LLM) error"""

    pass


class GitHubAPIError(ExternalServiceError):
    """GitHub API request failed"""

    pass


class LLMAPIError(ExternalServiceError):
    """LLM API request failed"""

    pass


# Made with Bob
