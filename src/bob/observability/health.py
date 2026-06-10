"""
IBM Bob - Health Checks
Comprehensive health check system for monitoring service and dependency health
"""

import asyncio
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, Optional

from bob.config import settings
from bob.observability.logging import get_logger

logger = get_logger(__name__)


class HealthStatus(str, Enum):
    """Health check status"""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class HealthCheckResult:
    """Result of a health check"""

    def __init__(
        self,
        status: HealthStatus,
        message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ):
        self.status = status
        self.message = message
        self.details = details or {}
        self.error = error
        self.timestamp = datetime.utcnow().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        result = {
            "status": self.status.value,
            "timestamp": self.timestamp,
        }
        if self.message:
            result["message"] = self.message
        if self.details:
            result["details"] = self.details
        if self.error:
            result["error"] = self.error
        return result


class HealthCheckManager:
    """
    Manages health checks for Bob and its dependencies.
    Provides liveness, readiness, and startup probes.
    """

    _instance: Optional["HealthCheckManager"] = None

    def __init__(self):
        """Initialize health check manager"""
        self.checks: Dict[str, Callable] = {}
        self._startup_complete = False

    def register_check(self, name: str, check_func: Callable):
        """
        Register a health check.

        Args:
            name: Check name
            check_func: Async function that returns HealthCheckResult
        """
        self.checks[name] = check_func
        logger.info("health_check_registered", check_name=name)

    def unregister_check(self, name: str):
        """
        Unregister a health check.

        Args:
            name: Check name
        """
        if name in self.checks:
            del self.checks[name]
            logger.info("health_check_unregistered", check_name=name)

    async def run_checks(self, timeout: float = 5.0) -> Dict[str, Any]:
        """
        Run all registered health checks.

        Args:
            timeout: Timeout for each check in seconds

        Returns:
            Dictionary with overall status and individual check results
        """
        results = {}
        overall_status = HealthStatus.HEALTHY

        for name, check_func in self.checks.items():
            try:
                # Run check with timeout
                result = await asyncio.wait_for(check_func(), timeout=timeout)

                if not isinstance(result, HealthCheckResult):
                    result = HealthCheckResult(
                        status=HealthStatus.UNHEALTHY,
                        error=f"Check returned invalid result type: {type(result)}",
                    )

                results[name] = result.to_dict()

                # Update overall status
                if result.status == HealthStatus.UNHEALTHY:
                    overall_status = HealthStatus.UNHEALTHY
                elif (
                    result.status == HealthStatus.DEGRADED
                    and overall_status == HealthStatus.HEALTHY
                ):
                    overall_status = HealthStatus.DEGRADED

            except asyncio.TimeoutError:
                logger.warning(
                    "health_check_timeout",
                    check_name=name,
                    timeout=timeout,
                )
                results[name] = HealthCheckResult(
                    status=HealthStatus.UNHEALTHY,
                    error=f"Check timed out after {timeout}s",
                ).to_dict()
                overall_status = HealthStatus.UNHEALTHY

            except Exception as e:
                logger.error(
                    "health_check_error",
                    check_name=name,
                    error=str(e),
                    exc_info=True,
                )
                results[name] = HealthCheckResult(
                    status=HealthStatus.UNHEALTHY,
                    error=str(e),
                ).to_dict()
                overall_status = HealthStatus.UNHEALTHY

        return {
            "status": overall_status.value,
            "checks": results,
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def liveness(self) -> Dict[str, Any]:
        """
        Liveness probe - is the service running?

        Returns:
            Liveness status
        """
        return {
            "status": HealthStatus.HEALTHY.value,
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def readiness(self) -> Dict[str, Any]:
        """
        Readiness probe - is the service ready to accept traffic?

        Returns:
            Readiness status with dependency checks
        """
        return await self.run_checks()

    async def startup(self) -> Dict[str, Any]:
        """
        Startup probe - has the service completed initialization?

        Returns:
            Startup status
        """
        if self._startup_complete:
            return {
                "status": HealthStatus.HEALTHY.value,
                "timestamp": datetime.utcnow().isoformat(),
            }
        else:
            return {
                "status": HealthStatus.UNHEALTHY.value,
                "message": "Startup not complete",
                "timestamp": datetime.utcnow().isoformat(),
            }

    def mark_startup_complete(self):
        """Mark startup as complete"""
        self._startup_complete = True
        logger.info("startup_complete")

    @classmethod
    def get_instance(cls) -> "HealthCheckManager":
        """
        Get singleton instance of HealthCheckManager.

        Returns:
            HealthCheckManager instance
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance


# ============================================================================
# Individual Health Checks
# ============================================================================


async def check_postgres() -> HealthCheckResult:
    """Check PostgreSQL connection"""
    try:
        import asyncpg

        conn = await asyncpg.connect(settings.postgres_dsn)
        await conn.execute("SELECT 1")
        await conn.close()

        return HealthCheckResult(
            status=HealthStatus.HEALTHY,
            message="PostgreSQL connection successful",
        )
    except Exception as e:
        logger.error("postgres_health_check_failed", error=str(e))
        return HealthCheckResult(
            status=HealthStatus.UNHEALTHY,
            message="PostgreSQL connection failed",
            error=str(e),
        )


async def check_neo4j() -> HealthCheckResult:
    """Check Neo4j connection"""
    try:
        from neo4j import AsyncGraphDatabase

        driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )

        async with driver.session() as session:
            result = await session.run("RETURN 1 as num")
            await result.single()

        await driver.close()

        return HealthCheckResult(
            status=HealthStatus.HEALTHY,
            message="Neo4j connection successful",
        )
    except Exception as e:
        logger.error("neo4j_health_check_failed", error=str(e))
        return HealthCheckResult(
            status=HealthStatus.UNHEALTHY,
            message="Neo4j connection failed",
            error=str(e),
        )


async def check_redis() -> HealthCheckResult:
    """Check Redis connection"""
    try:
        import redis.asyncio as redis

        client = redis.from_url(settings.redis_url)
        await client.ping()
        await client.close()

        return HealthCheckResult(
            status=HealthStatus.HEALTHY,
            message="Redis connection successful",
        )
    except Exception as e:
        logger.error("redis_health_check_failed", error=str(e))
        return HealthCheckResult(
            status=HealthStatus.UNHEALTHY,
            message="Redis connection failed",
            error=str(e),
        )


async def check_weaviate() -> HealthCheckResult:
    """Check Weaviate connection"""
    try:
        import weaviate

        client = weaviate.Client(settings.weaviate_url)
        is_ready = client.is_ready()

        if is_ready:
            return HealthCheckResult(
                status=HealthStatus.HEALTHY,
                message="Weaviate connection successful",
            )
        else:
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                message="Weaviate not ready",
            )
    except Exception as e:
        logger.error("weaviate_health_check_failed", error=str(e))
        return HealthCheckResult(
            status=HealthStatus.UNHEALTHY,
            message="Weaviate connection failed",
            error=str(e),
        )


# Convenience functions
def get_health_manager() -> HealthCheckManager:
    """Get HealthCheckManager instance"""
    return HealthCheckManager.get_instance()


def register_default_checks():
    """Register default health checks for all dependencies"""
    manager = get_health_manager()
    manager.register_check("postgres", check_postgres)
    manager.register_check("neo4j", check_neo4j)
    manager.register_check("redis", check_redis)
    manager.register_check("weaviate", check_weaviate)
    logger.info("default_health_checks_registered")


# Made with Bob
