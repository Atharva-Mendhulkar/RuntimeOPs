"""
IBM Bob - Query Gateway
Handles authentication, rate limiting, and request logging for all queries
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

import jwt
import redis
from fastapi import Header, HTTPException, Request

from bob.config import get_settings
from bob.exceptions import (
    AuthenticationError,
    InvalidTokenError,
    RateLimitExceededError,
)

logger = logging.getLogger(__name__)


class QueryGateway:
    """
    Query gateway for authentication, rate limiting, and logging.

    Responsibilities:
    - Verify RuntimeOps internal JWT tokens
    - Extract repo_id and org_id from token claims
    - Rate limiting: 500 req/min per agent, burst to 1000 req/min
    - Request logging (excluding sensitive data per FR-025)
    - Distributed rate limit counters using Redis
    """

    def __init__(self) -> None:
        """Initialize the query gateway"""
        self.settings = get_settings()
        self._redis_client: redis.Redis | None = None
        self._rate_limit_per_minute = self.settings.rate_limit_per_minute
        self._rate_limit_burst = self.settings.rate_limit_burst
        self._burst_window_seconds = 10

    def connect(self) -> None:
        """Connect to Redis for rate limiting"""
        try:
            self._redis_client = redis.Redis(
                host=self.settings.redis_host,
                port=self.settings.redis_port,
                password=self.settings.redis_password,
                db=self.settings.redis_db,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
            self._redis_client.ping()
            logger.info("Query gateway connected to Redis")
        except redis.RedisError as e:
            logger.error(f"Failed to connect to Redis for rate limiting: {e}")
            raise

    def close(self) -> None:
        """Close Redis connection"""
        if self._redis_client:
            self._redis_client.close()
            logger.info("Query gateway closed Redis connection")

    def verify_token(self, authorization: str | None = None) -> dict[str, Any]:
        """
        Verify RuntimeOps internal JWT token.

        Args:
            authorization: Authorization header value (Bearer <token>)

        Returns:
            Dictionary with token claims (repo_id, org_id, etc.)

        Raises:
            AuthenticationError: If token is missing or invalid
            InvalidTokenError: If token is expired or malformed
        """
        if not authorization:
            raise AuthenticationError(
                "Missing authorization header",
                details={"required": "Bearer <token>"},
            )

        # Extract token from "Bearer <token>"
        parts = authorization.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise AuthenticationError(
                "Invalid authorization header format",
                details={"expected": "Bearer <token>", "received": authorization[:20]},
            )

        token = parts[1]

        try:
            # Decode and verify JWT
            payload = jwt.decode(
                token,
                self.settings.jwt_secret_key,
                algorithms=[self.settings.jwt_algorithm],
            )

            # Validate required claims
            required_claims = ["repo_id", "org_id", "exp"]
            missing_claims = [claim for claim in required_claims if claim not in payload]

            if missing_claims:
                raise InvalidTokenError(
                    f"Missing required claims: {', '.join(missing_claims)}",
                    details={"missing": missing_claims},
                )

            # Validate repo_id format
            try:
                UUID(payload["repo_id"])
            except (ValueError, TypeError) as e:
                raise InvalidTokenError(
                    "Invalid repo_id format in token",
                    details={"repo_id": payload.get("repo_id")},
                ) from e

            logger.debug(
                f"Token verified for repo_id={payload['repo_id']}, org_id={payload['org_id']}"
            )
            return payload

        except jwt.ExpiredSignatureError as e:
            raise InvalidTokenError(
                "Token has expired",
                details={"error": "expired_signature"},
            ) from e
        except jwt.InvalidTokenError as e:
            raise InvalidTokenError(
                f"Invalid token: {str(e)}",
                details={"error": str(e)},
            ) from e

    def check_rate_limit(self, agent_id: str) -> None:
        """
        Check rate limit for agent.

        Rate limits:
        - 500 requests per minute (normal)
        - 1000 requests per minute burst (10 second window)

        Args:
            agent_id: Agent identifier (typically org_id or agent instance ID)

        Raises:
            RateLimitExceededError: If rate limit is exceeded
        """
        if not self._redis_client:
            logger.warning("Redis not connected, skipping rate limit check")
            return

        current_time = int(time.time())
        minute_key = f"bob:ratelimit:{agent_id}:minute:{current_time // 60}"
        burst_key = f"bob:ratelimit:{agent_id}:burst:{current_time // self._burst_window_seconds}"

        try:
            # Check burst limit (1000 req / 10 seconds)
            burst_count = self._redis_client.incr(burst_key)
            if burst_count == 1:
                self._redis_client.expire(burst_key, self._burst_window_seconds)

            if burst_count > self._rate_limit_burst:
                logger.warning(
                    f"Burst rate limit exceeded for agent {agent_id}: {burst_count}/{self._rate_limit_burst}"
                )
                raise RateLimitExceededError(
                    f"Burst rate limit exceeded: {burst_count}/{self._rate_limit_burst} requests in {self._burst_window_seconds}s",
                    details={
                        "agent_id": agent_id,
                        "limit": self._rate_limit_burst,
                        "window_seconds": self._burst_window_seconds,
                        "current_count": burst_count,
                    },
                )

            # Check per-minute limit (500 req / minute)
            minute_count = self._redis_client.incr(minute_key)
            if minute_count == 1:
                self._redis_client.expire(minute_key, 60)

            if minute_count > self._rate_limit_per_minute:
                logger.warning(
                    f"Rate limit exceeded for agent {agent_id}: {minute_count}/{self._rate_limit_per_minute}"
                )
                raise RateLimitExceededError(
                    f"Rate limit exceeded: {minute_count}/{self._rate_limit_per_minute} requests per minute",
                    details={
                        "agent_id": agent_id,
                        "limit": self._rate_limit_per_minute,
                        "window_seconds": 60,
                        "current_count": minute_count,
                    },
                )

            logger.debug(
                f"Rate limit check passed for {agent_id}: minute={minute_count}/{self._rate_limit_per_minute}, "
                f"burst={burst_count}/{self._rate_limit_burst}"
            )

        except redis.RedisError as e:
            logger.error(f"Redis error during rate limit check: {e}")
            # Fail open - allow request if Redis is down
            return

    def log_request(
        self,
        request: Request,
        claims: dict[str, Any],
        endpoint: str,
        duration_ms: float | None = None,
        status_code: int | None = None,
        error: str | None = None,
    ) -> None:
        """
        Log request details (excluding sensitive data per FR-025).

        Args:
            request: FastAPI request object
            claims: Token claims
            endpoint: API endpoint
            duration_ms: Request duration in milliseconds
            status_code: HTTP status code
            error: Error message if request failed
        """
        # Extract non-sensitive request details
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "endpoint": endpoint,
            "method": request.method,
            "repo_id": claims.get("repo_id"),
            "org_id": claims.get("org_id"),
            "client_ip": request.client.host if request.client else None,
            "user_agent": request.headers.get("user-agent"),
            "duration_ms": duration_ms,
            "status_code": status_code,
        }

        if error:
            log_data["error"] = error

        # Log at appropriate level
        if status_code and status_code >= 500:
            logger.error(f"Request failed: {log_data}")
        elif status_code and status_code >= 400:
            logger.warning(f"Request error: {log_data}")
        else:
            logger.info(f"Request completed: {log_data}")

    async def authenticate_request(
        self,
        request: Request,
        authorization: str | None = Header(None),
    ) -> dict[str, Any]:
        """
        Authenticate and authorize a request.

        This is the main entry point for request authentication.

        Args:
            request: FastAPI request object
            authorization: Authorization header

        Returns:
            Token claims dictionary

        Raises:
            HTTPException: If authentication or rate limiting fails
        """
        start_time = time.time()

        try:
            # Verify JWT token
            claims = self.verify_token(authorization)

            # Check rate limit
            agent_id = claims.get("org_id", "unknown")
            self.check_rate_limit(agent_id)

            # Log successful authentication
            duration_ms = (time.time() - start_time) * 1000
            self.log_request(
                request=request,
                claims=claims,
                endpoint=request.url.path,
                duration_ms=duration_ms,
                status_code=200,
            )

            return claims

        except AuthenticationError as e:
            duration_ms = (time.time() - start_time) * 1000
            self.log_request(
                request=request,
                claims={},
                endpoint=request.url.path,
                duration_ms=duration_ms,
                status_code=401,
                error=e.message,
            )
            raise HTTPException(status_code=401, detail=e.message)

        except InvalidTokenError as e:
            duration_ms = (time.time() - start_time) * 1000
            self.log_request(
                request=request,
                claims={},
                endpoint=request.url.path,
                duration_ms=duration_ms,
                status_code=401,
                error=e.message,
            )
            raise HTTPException(status_code=401, detail=e.message)

        except RateLimitExceededError as e:
            duration_ms = (time.time() - start_time) * 1000
            self.log_request(
                request=request,
                claims={},
                endpoint=request.url.path,
                duration_ms=duration_ms,
                status_code=429,
                error=e.message,
            )
            raise HTTPException(
                status_code=429,
                detail=e.message,
                headers={"Retry-After": "60"},
            )

    def get_rate_limit_stats(self, agent_id: str) -> dict[str, Any]:
        """
        Get rate limit statistics for an agent.

        Args:
            agent_id: Agent identifier

        Returns:
            Dictionary with rate limit stats
        """
        if not self._redis_client:
            return {"error": "Redis not connected"}

        current_time = int(time.time())
        minute_key = f"bob:ratelimit:{agent_id}:minute:{current_time // 60}"
        burst_key = f"bob:ratelimit:{agent_id}:burst:{current_time // self._burst_window_seconds}"

        try:
            minute_count = int(self._redis_client.get(minute_key) or 0)
            burst_count = int(self._redis_client.get(burst_key) or 0)

            return {
                "agent_id": agent_id,
                "minute_count": minute_count,
                "minute_limit": self._rate_limit_per_minute,
                "minute_remaining": max(0, self._rate_limit_per_minute - minute_count),
                "burst_count": burst_count,
                "burst_limit": self._rate_limit_burst,
                "burst_remaining": max(0, self._rate_limit_burst - burst_count),
            }

        except redis.RedisError as e:
            logger.error(f"Failed to get rate limit stats: {e}")
            return {"error": str(e)}


# Global gateway instance
_gateway: QueryGateway | None = None


def get_gateway() -> QueryGateway:
    """
    Get or create the global query gateway instance.

    Returns:
        QueryGateway instance
    """
    global _gateway
    if _gateway is None:
        _gateway = QueryGateway()
        _gateway.connect()
    return _gateway


# Made with Bob
