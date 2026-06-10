"""
IBM Bob - Rate Limiting
Multi-tier rate limiting with Redis-backed sliding window
"""

import time
from enum import Enum
from typing import Any, Dict, Optional, Tuple

from redis import Redis

from bob.exceptions import RateLimitExceededError


class RateLimitTier(str, Enum):
    """Rate limit tiers for different user types"""

    FREE = "free"
    DEVELOPER = "developer"
    TEAM = "team"
    ENTERPRISE = "enterprise"


# Rate limit configurations per tier
RATE_LIMITS: Dict[RateLimitTier, Dict[str, int]] = {
    RateLimitTier.FREE: {
        "requests_per_hour": 100,
        "requests_per_minute": 10,
        "concurrent_requests": 2,
        "burst_allowance": 5,
    },
    RateLimitTier.DEVELOPER: {
        "requests_per_hour": 1000,
        "requests_per_minute": 50,
        "concurrent_requests": 5,
        "burst_allowance": 20,
    },
    RateLimitTier.TEAM: {
        "requests_per_hour": 10000,
        "requests_per_minute": 200,
        "concurrent_requests": 20,
        "burst_allowance": 100,
    },
    RateLimitTier.ENTERPRISE: {
        "requests_per_hour": 100000,
        "requests_per_minute": 2000,
        "concurrent_requests": 100,
        "burst_allowance": 500,
    },
}

# Per-endpoint rate limit multipliers (relative to base limits)
ENDPOINT_MULTIPLIERS: Dict[str, float] = {
    "/api/v1/bob/search": 0.5,  # More expensive, lower limit
    "/api/v1/bob/resolve-stack-trace": 0.7,
    "/api/v1/bob/dependency-graph": 0.8,
    "/api/v1/bob/blast-radius": 0.5,  # Most expensive
    "/api/v1/bob/file": 1.0,
    "/api/v1/bob/commit-diff": 0.8,
    "/api/v1/bob/batch": 0.3,  # Very expensive
    "/api/v1/bob/health": 10.0,  # Very cheap, higher limit
}


class RateLimiter:
    """Redis-backed rate limiter using sliding window algorithm"""

    def __init__(self, redis_client: Redis):
        """
        Initialize rate limiter.

        Args:
            redis_client: Redis client for distributed rate limiting
        """
        self.redis = redis_client

    async def check_rate_limit(
        self,
        user_id: str,
        endpoint: str,
        tier: RateLimitTier = RateLimitTier.FREE,
    ) -> Tuple[bool, Dict[str, int]]:
        """
        Check if request is within rate limits.

        Args:
            user_id: User identifier
            endpoint: API endpoint path
            tier: User's rate limit tier

        Returns:
            Tuple of (allowed, metadata) where metadata contains:
            - remaining: Requests remaining in current window
            - reset_at: Unix timestamp when limit resets
            - retry_after: Seconds to wait if rate limited

        Raises:
            RateLimitExceededError: If rate limit exceeded
        """
        now = int(time.time())
        limits = RATE_LIMITS[tier]
        multiplier = ENDPOINT_MULTIPLIERS.get(endpoint, 1.0)

        # Calculate effective limits for this endpoint
        hourly_limit = int(limits["requests_per_hour"] * multiplier)
        minute_limit = int(limits["requests_per_minute"] * multiplier)

        # Check hourly limit
        hourly_key = f"ratelimit:hour:{user_id}:{endpoint}"
        hourly_count = self._get_request_count(hourly_key, 3600, now)

        if hourly_count >= hourly_limit:
            reset_at = self._get_window_reset(hourly_key, 3600, now)
            retry_after = reset_at - now

            raise RateLimitExceededError(
                f"Hourly rate limit exceeded. Limit: {hourly_limit}/hour. "
                f"Retry after {retry_after} seconds.",
                details={
                    "limit": hourly_limit,
                    "remaining": 0,
                    "reset_at": reset_at,
                    "retry_after": retry_after,
                },
            )

        # Check minute limit
        minute_key = f"ratelimit:minute:{user_id}:{endpoint}"
        minute_count = self._get_request_count(minute_key, 60, now)

        if minute_count >= minute_limit:
            reset_at = self._get_window_reset(minute_key, 60, now)
            retry_after = reset_at - now

            raise RateLimitExceededError(
                f"Per-minute rate limit exceeded. Limit: {minute_limit}/min. "
                f"Retry after {retry_after} seconds.",
                details={
                    "limit": minute_limit,
                    "remaining": 0,
                    "reset_at": reset_at,
                    "retry_after": retry_after,
                },
            )

        # Check burst allowance
        burst_key = f"ratelimit:burst:{user_id}"
        burst_count = self._get_request_count(burst_key, 10, now)
        burst_limit = limits["burst_allowance"]

        if burst_count >= burst_limit:
            reset_at = self._get_window_reset(burst_key, 10, now)
            retry_after = reset_at - now

            raise RateLimitExceededError(
                f"Burst limit exceeded. Limit: {burst_limit}/10s. "
                f"Retry after {retry_after} seconds.",
                details={
                    "limit": burst_limit,
                    "remaining": 0,
                    "reset_at": reset_at,
                    "retry_after": retry_after,
                },
            )

        # Calculate remaining requests (use most restrictive limit)
        hourly_remaining = hourly_limit - hourly_count
        minute_remaining = minute_limit - minute_count
        remaining = min(hourly_remaining, minute_remaining)

        # Calculate next reset time (use nearest reset)
        hourly_reset = self._get_window_reset(hourly_key, 3600, now)
        minute_reset = self._get_window_reset(minute_key, 60, now)
        reset_at = min(hourly_reset, minute_reset)

        return True, {
            "remaining": remaining,
            "reset_at": reset_at,
            "retry_after": 0,
        }

    async def record_request(
        self,
        user_id: str,
        endpoint: str,
        tier: RateLimitTier = RateLimitTier.FREE,
    ) -> None:
        """
        Record a request for rate limiting.

        Args:
            user_id: User identifier
            endpoint: API endpoint path
            tier: User's rate limit tier
        """
        now = int(time.time())

        # Record in hourly window
        hourly_key = f"ratelimit:hour:{user_id}:{endpoint}"
        self._record_in_window(hourly_key, 3600, now)

        # Record in minute window
        minute_key = f"ratelimit:minute:{user_id}:{endpoint}"
        self._record_in_window(minute_key, 60, now)

        # Record in burst window
        burst_key = f"ratelimit:burst:{user_id}"
        self._record_in_window(burst_key, 10, now)

    async def get_usage_stats(
        self,
        user_id: str,
        tier: RateLimitTier = RateLimitTier.FREE,
    ) -> Dict[str, Any]:
        """
        Get current usage statistics for a user.

        Args:
            user_id: User identifier
            tier: User's rate limit tier

        Returns:
            Dictionary with usage statistics
        """
        now = int(time.time())
        limits = RATE_LIMITS[tier]

        # Get hourly usage across all endpoints
        pattern = f"ratelimit:hour:{user_id}:*"
        hourly_keys = self.redis.keys(pattern)
        total_hourly = sum(self._get_request_count(key.decode(), 3600, now) for key in hourly_keys)

        # Get minute usage
        pattern = f"ratelimit:minute:{user_id}:*"
        minute_keys = self.redis.keys(pattern)
        total_minute = sum(self._get_request_count(key.decode(), 60, now) for key in minute_keys)

        return {
            "tier": tier.value,
            "hourly": {
                "used": total_hourly,
                "limit": limits["requests_per_hour"],
                "remaining": max(0, limits["requests_per_hour"] - total_hourly),
            },
            "minute": {
                "used": total_minute,
                "limit": limits["requests_per_minute"],
                "remaining": max(0, limits["requests_per_minute"] - total_minute),
            },
            "concurrent_limit": limits["concurrent_requests"],
        }

    def _get_request_count(self, key: str, window_seconds: int, now: int) -> int:
        """
        Get request count in sliding window.

        Uses Redis sorted set with timestamps as scores.
        """
        # Remove old entries outside window
        window_start = now - window_seconds
        self.redis.zremrangebyscore(key, 0, window_start)

        # Count entries in current window
        count = self.redis.zcard(key)
        return count

    def _record_in_window(self, key: str, window_seconds: int, now: int) -> None:
        """
        Record a request in sliding window.

        Uses Redis sorted set with timestamps as scores.
        """
        # Add current request with timestamp as score
        self.redis.zadd(key, {f"{now}:{time.time_ns()}": now})

        # Set expiration to window size + buffer
        self.redis.expire(key, window_seconds + 60)

    def _get_window_reset(self, key: str, window_seconds: int, now: int) -> int:
        """Get timestamp when the rate limit window resets"""
        # Get oldest entry in window
        oldest = self.redis.zrange(key, 0, 0, withscores=True)

        if oldest:
            oldest_timestamp = int(oldest[0][1])
            return oldest_timestamp + window_seconds

        # If no entries, reset is now + window
        return now + window_seconds

    async def check_concurrent_requests(
        self,
        user_id: str,
        tier: RateLimitTier = RateLimitTier.FREE,
    ) -> bool:
        """
        Check if user is within concurrent request limit.

        Args:
            user_id: User identifier
            tier: User's rate limit tier

        Returns:
            True if within limit

        Raises:
            RateLimitExceededError: If concurrent limit exceeded
        """
        limits = RATE_LIMITS[tier]
        concurrent_limit = limits["concurrent_requests"]

        key = f"concurrent:{user_id}"
        current = self.redis.get(key)
        current_count = int(current) if current else 0

        if current_count >= concurrent_limit:
            raise RateLimitExceededError(
                f"Concurrent request limit exceeded. Limit: {concurrent_limit}",
                details={
                    "limit": concurrent_limit,
                    "current": current_count,
                },
            )

        return True

    async def increment_concurrent(self, user_id: str) -> None:
        """Increment concurrent request counter"""
        key = f"concurrent:{user_id}"
        self.redis.incr(key)
        self.redis.expire(key, 300)  # 5 minute expiration

    async def decrement_concurrent(self, user_id: str) -> None:
        """Decrement concurrent request counter"""
        key = f"concurrent:{user_id}"
        current = self.redis.get(key)

        if current and int(current) > 0:
            self.redis.decr(key)

    def get_tier_for_user(self, user_id: str) -> RateLimitTier:
        """
        Get rate limit tier for user.

        This would typically query a database. For now, returns default.

        Args:
            user_id: User identifier

        Returns:
            User's rate limit tier
        """
        # TODO: Query database for user's tier
        # For now, return default tier
        return RateLimitTier.FREE


def get_rate_limit_headers(
    limit: int,
    remaining: int,
    reset_at: int,
) -> Dict[str, str]:
    """
    Generate rate limit headers for HTTP response.

    Args:
        limit: Total requests allowed in window
        remaining: Requests remaining
        reset_at: Unix timestamp when limit resets

    Returns:
        Dictionary of headers
    """
    return {
        "X-RateLimit-Limit": str(limit),
        "X-RateLimit-Remaining": str(remaining),
        "X-RateLimit-Reset": str(reset_at),
    }


# Made with Bob
