"""
IBM Bob - Security Middleware
FastAPI middleware for authentication, authorization, and rate limiting
"""

import logging
import time
from typing import Any, Callable, Dict, Optional
from uuid import uuid4

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware

from bob.config import get_settings
from bob.exceptions import (
    AuthenticationError,
    AuthorizationError,
    InvalidTokenError,
    RateLimitExceededError,
)
from bob.security.audit import AuditEventType, AuditLogger
from bob.security.auth import APIKeyManager, JWTManager
from bob.security.rate_limiter import RateLimiter, get_rate_limit_headers
from bob.security.rbac import AuthorizationChecker
from bob.security.validation import sanitize_error_message

logger = logging.getLogger(__name__)
settings = get_settings()


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses"""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable,
    ) -> Response:
        """
        Add security headers to response.

        Headers added:
        - X-Content-Type-Options: nosniff
        - X-Frame-Options: DENY
        - X-XSS-Protection: 1; mode=block
        - Strict-Transport-Security: max-age=31536000
        - Content-Security-Policy: default-src 'self'
        - X-Request-ID: Unique request identifier
        """
        # Generate request ID
        request_id = str(uuid4())
        request.state.request_id = request_id

        # Process request
        response = await call_next(request)

        # Add security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Content-Security-Policy"] = "default-src 'self'"
        response.headers["X-Request-ID"] = request_id

        # Add HSTS header in production
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        return response


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """Verify JWT tokens or API keys on protected endpoints"""

    # Public endpoints that don't require authentication
    PUBLIC_ENDPOINTS = {
        "/api/v1/bob/health",
        "/docs",
        "/redoc",
        "/openapi.json",
    }

    def __init__(self, app, jwt_manager: JWTManager, api_key_manager: APIKeyManager):
        """
        Initialize authentication middleware.

        Args:
            app: FastAPI application
            jwt_manager: JWT manager instance
            api_key_manager: API key manager instance
        """
        super().__init__(app)
        self.jwt_manager = jwt_manager
        self.api_key_manager = api_key_manager

    async def dispatch(
        self,
        request: Request,
        call_next: Callable,
    ) -> Response:
        """Authenticate request"""
        # Skip authentication for public endpoints
        if request.url.path in self.PUBLIC_ENDPOINTS:
            return await call_next(request)

        try:
            # Extract authorization header
            authorization = request.headers.get("Authorization")

            if not authorization:
                raise AuthenticationError("Missing Authorization header")

            # Determine authentication method
            if authorization.startswith("Bearer "):
                # JWT authentication
                token = authorization[7:]  # Remove "Bearer " prefix
                claims = self.jwt_manager.verify_token(token)
                request.state.user_id = claims["sub"]
                request.state.scopes = claims.get("scopes", [])
                request.state.auth_method = "jwt"

            elif authorization.startswith("ApiKey "):
                # API key authentication
                api_key = authorization[7:]  # Remove "ApiKey " prefix
                claims = self.api_key_manager.verify_api_key(api_key)
                request.state.user_id = claims["user_id"]
                request.state.scopes = claims["scopes"]
                request.state.auth_method = "api_key"
                request.state.api_key_id = claims["key_id"]

            else:
                raise AuthenticationError(
                    "Invalid Authorization header format. Use 'Bearer <token>' or 'ApiKey <key>'"
                )

            # Process request
            response = await call_next(request)
            return response

        except (AuthenticationError, InvalidTokenError) as e:
            logger.warning(f"Authentication failed: {e}")

            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={
                    "error": "authentication_failed",
                    "message": str(e),
                    "request_id": getattr(request.state, "request_id", None),
                },
                headers={"WWW-Authenticate": "Bearer"},
            )

        except Exception as e:
            logger.error(f"Authentication error: {e}", exc_info=True)

            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "error": "internal_error",
                    "message": "Authentication failed",
                    "request_id": getattr(request.state, "request_id", None),
                },
            )


class AuthorizationMiddleware(BaseHTTPMiddleware):
    """Check user permissions for endpoints"""

    def __init__(self, app, authz_checker: AuthorizationChecker):
        """
        Initialize authorization middleware.

        Args:
            app: FastAPI application
            authz_checker: Authorization checker instance
        """
        super().__init__(app)
        self.authz_checker = authz_checker

    async def dispatch(
        self,
        request: Request,
        call_next: Callable,
    ) -> Response:
        """Check authorization"""
        # Skip if no user (public endpoint)
        if not hasattr(request.state, "user_id"):
            return await call_next(request)

        try:
            # Check endpoint permission
            user_scopes = getattr(request.state, "scopes", [])
            endpoint = request.url.path

            self.authz_checker.check_endpoint_permission(user_scopes, endpoint)

            # Process request
            response = await call_next(request)
            return response

        except AuthorizationError as e:
            logger.warning(f"Authorization failed for user {request.state.user_id}: {e}")

            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={
                    "error": "authorization_failed",
                    "message": str(e),
                    "request_id": getattr(request.state, "request_id", None),
                },
            )

        except Exception as e:
            logger.error(f"Authorization error: {e}", exc_info=True)

            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "error": "internal_error",
                    "message": "Authorization check failed",
                    "request_id": getattr(request.state, "request_id", None),
                },
            )


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Apply rate limits to requests"""

    def __init__(self, app, rate_limiter: RateLimiter):
        """
        Initialize rate limit middleware.

        Args:
            app: FastAPI application
            rate_limiter: Rate limiter instance
        """
        super().__init__(app)
        self.rate_limiter = rate_limiter

    async def dispatch(
        self,
        request: Request,
        call_next: Callable,
    ) -> Response:
        """Check and enforce rate limits"""
        # Skip if no user (public endpoint)
        if not hasattr(request.state, "user_id"):
            return await call_next(request)

        user_id = request.state.user_id
        endpoint = request.url.path

        try:
            # Get user's rate limit tier
            tier = self.rate_limiter.get_tier_for_user(user_id)

            # Check concurrent requests
            await self.rate_limiter.check_concurrent_requests(user_id, tier)
            await self.rate_limiter.increment_concurrent(user_id)

            try:
                # Check rate limit
                allowed, metadata = await self.rate_limiter.check_rate_limit(
                    user_id, endpoint, tier
                )

                # Record request
                await self.rate_limiter.record_request(user_id, endpoint, tier)

                # Process request
                response = await call_next(request)

                # Add rate limit headers
                response.headers.update(
                    get_rate_limit_headers(
                        limit=metadata.get("remaining", 0) + 1,
                        remaining=metadata["remaining"],
                        reset_at=metadata["reset_at"],
                    )
                )

                return response

            finally:
                # Always decrement concurrent counter
                await self.rate_limiter.decrement_concurrent(user_id)

        except RateLimitExceededError as e:
            logger.warning(f"Rate limit exceeded for user {user_id}: {e}")

            # Get retry-after from exception details
            retry_after = e.details.get("retry_after", 60)

            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": "rate_limit_exceeded",
                    "message": str(e),
                    "retry_after": retry_after,
                    "request_id": getattr(request.state, "request_id", None),
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(e.details.get("limit", 0)),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(e.details.get("reset_at", 0)),
                },
            )

        except Exception as e:
            logger.error(f"Rate limit error: {e}", exc_info=True)

            # Don't block request on rate limiter errors
            return await call_next(request)


class AuditLoggingMiddleware(BaseHTTPMiddleware):
    """Log all requests for audit trail"""

    def __init__(self, app, audit_logger: AuditLogger):
        """
        Initialize audit logging middleware.

        Args:
            app: FastAPI application
            audit_logger: Audit logger instance
        """
        super().__init__(app)
        self.audit_logger = audit_logger

    async def dispatch(
        self,
        request: Request,
        call_next: Callable,
    ) -> Response:
        """Log request and response"""
        start_time = time.time()

        # Get request metadata
        user_id = getattr(request.state, "user_id", "anonymous")
        request_id = getattr(request.state, "request_id", None)
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("User-Agent")

        try:
            # Process request
            response = await call_next(request)

            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000

            # Log successful request
            if response.status_code < 400:
                # Only log data access events, not health checks
                if request.url.path != "/api/v1/bob/health":
                    self._log_data_access(
                        user_id=user_id,
                        endpoint=request.url.path,
                        method=request.method,
                        status_code=response.status_code,
                        duration_ms=duration_ms,
                        ip_address=ip_address,
                        user_agent=user_agent,
                        request_id=request_id,
                    )

            return response

        except Exception as e:
            # Log failed request
            duration_ms = (time.time() - start_time) * 1000

            self.audit_logger.log_event(
                event_type=AuditEventType.ACCESS_DENIED,
                user_id=user_id,
                resource=request.url.path,
                action=request.method,
                result="failure",
                metadata={
                    "error": sanitize_error_message(str(e)),
                    "duration_ms": duration_ms,
                },
                ip_address=ip_address,
                user_agent=user_agent,
                request_id=request_id,
            )

            raise

    def _log_data_access(
        self,
        user_id: str,
        endpoint: str,
        method: str,
        status_code: int,
        duration_ms: float,
        ip_address: Optional[str],
        user_agent: Optional[str],
        request_id: Optional[str],
    ) -> None:
        """Log data access event"""
        # Determine event type based on endpoint
        event_type_map = {
            "/api/v1/bob/search": AuditEventType.SEARCH_EXECUTED,
            "/api/v1/bob/file": AuditEventType.FILE_ACCESSED,
            "/api/v1/bob/dependency-graph": AuditEventType.DEPENDENCY_GRAPH_QUERIED,
            "/api/v1/bob/blast-radius": AuditEventType.BLAST_RADIUS_COMPUTED,
        }

        event_type = event_type_map.get(endpoint, AuditEventType.REPOSITORY_ACCESSED)

        self.audit_logger.log_event(
            event_type=event_type,
            user_id=user_id,
            resource=endpoint,
            action=method,
            result="success",
            metadata={
                "status_code": status_code,
                "duration_ms": duration_ms,
            },
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
        )


def setup_cors_middleware(app, allowed_origins: Optional[list[str]] = None):
    """
    Configure CORS middleware for frontend access.

    Args:
        app: FastAPI application
        allowed_origins: List of allowed origins (defaults to settings)
    """
    if allowed_origins is None:
        allowed_origins = settings.cors_origins if hasattr(settings, "cors_origins") else ["*"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=[
            "X-Request-ID",
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "X-RateLimit-Reset",
        ],
    )


# Made with Bob
