"""
IBM Bob - Security Module
Authentication, authorization, rate limiting, and audit logging
"""

from bob.security.audit import AuditEventType, AuditLogger
from bob.security.auth import APIKeyManager, JWTManager
from bob.security.middleware import (
    AuditLoggingMiddleware,
    AuthenticationMiddleware,
    AuthorizationMiddleware,
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
    setup_cors_middleware,
)
from bob.security.rate_limiter import RateLimiter, RateLimitTier
from bob.security.rbac import (
    AuthorizationChecker,
    Role,
    Scope,
    get_scopes_for_role,
    validate_scopes,
)
from bob.security.secrets import (
    SecretString,
    SecretsManager,
    generate_encryption_key,
    mask_secret,
    sanitize_for_logging,
    validate_encryption_key,
    validate_required_secrets,
)
from bob.security.validation import (
    QueryValidator,
    RequestValidator,
    sanitize_error_message,
)

__all__ = [
    # Authentication
    "JWTManager",
    "APIKeyManager",
    # Authorization
    "AuthorizationChecker",
    "Role",
    "Scope",
    "get_scopes_for_role",
    "validate_scopes",
    # Rate Limiting
    "RateLimiter",
    "RateLimitTier",
    # Audit Logging
    "AuditLogger",
    "AuditEventType",
    # Secrets Management
    "SecretsManager",
    "SecretString",
    "generate_encryption_key",
    "mask_secret",
    "validate_encryption_key",
    "validate_required_secrets",
    "sanitize_for_logging",
    # Validation
    "QueryValidator",
    "RequestValidator",
    "sanitize_error_message",
    # Middleware
    "SecurityHeadersMiddleware",
    "AuthenticationMiddleware",
    "AuthorizationMiddleware",
    "RateLimitMiddleware",
    "AuditLoggingMiddleware",
    "setup_cors_middleware",
]

# Made with Bob