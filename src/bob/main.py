"""
IBM Bob - Main Application Entry Point
FastAPI application with health check endpoint
"""

import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from bob.config import settings
from bob.observability.health import (
    HealthCheckManager,
    register_default_checks,
)
from bob.observability.logging import get_logger
from bob.observability.metrics import get_metrics_manager
from bob.observability.middleware import (
    ErrorHandlingMiddleware,
    LoggingMiddleware,
    MetricsMiddleware,
    TracingMiddleware,
)
from bob.observability.tracing import TracingManager
from bob.query.gateway import get_gateway

# Version info
__version__ = "1.0.0"

# Initialize logger
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan manager.
    Handles startup and shutdown events.
    """
    # Startup
    logger.info("starting_bob", version=__version__, environment=settings.environment)
    print(f"🚀 Starting IBM Bob v{__version__}")
    print(f"📍 Environment: {settings.environment}")
    print(f"🔧 Neo4j: {settings.neo4j_uri}")
    print(f"🔧 Weaviate: {settings.weaviate_url}")
    print(f"🔧 PostgreSQL: {settings.postgres_host}:{settings.postgres_port}")
    print(f"🔧 Redis: {settings.redis_host}:{settings.redis_port}")

    # Initialize observability
    try:
        # Initialize tracing
        if settings.enable_tracing:
            tracing_manager = TracingManager.get_instance()
            tracing_manager.instrument_fastapi(app)
            logger.info("tracing_initialized")
            print("✅ Tracing initialized")

        # Initialize metrics
        if settings.enable_metrics:
            metrics_manager = get_metrics_manager()
            logger.info("metrics_initialized")
            print("✅ Metrics initialized")

        # Initialize health checks
        health_manager = HealthCheckManager.get_instance()
        register_default_checks()
        logger.info("health_checks_initialized")
        print("✅ Health checks initialized")

    except Exception as e:
        logger.error("observability_initialization_failed", error=str(e), exc_info=True)
        print(f"⚠️  Observability initialization failed: {e}")

    # Initialize query gateway
    try:
        gateway = get_gateway()
        logger.info("query_gateway_initialized")
        print("✅ Query gateway initialized")
    except Exception as e:
        logger.error("query_gateway_initialization_failed", error=str(e), exc_info=True)
        print(f"⚠️  Query gateway initialization failed: {e}")

    # Start gRPC server
    grpc_server = None
    try:
        from bob.api.grpc_server import GRPCServer
        grpc_server = GRPCServer(host=settings.api_host, port=settings.grpc_port)
        await grpc_server.start()
        logger.info("grpc_server_started", port=settings.grpc_port)
        print(f"✅ gRPC server started on port {settings.grpc_port}")
        app.state.grpc_server = grpc_server
    except Exception as e:
        logger.error("grpc_server_startup_failed", error=str(e), exc_info=True)
        print(f"⚠️  gRPC server startup failed: {e}")

    # Mark startup as complete
    try:
        health_manager = HealthCheckManager.get_instance()
        health_manager.mark_startup_complete()
        logger.info("startup_complete")
        print("✅ Startup complete")
    except Exception as e:
        logger.error("startup_completion_failed", error=str(e), exc_info=True)

    yield

    # Shutdown
    logger.info("shutting_down_bob")
    print("🛑 Shutting down IBM Bob")
    
    # Stop gRPC server
    try:
        grpc_server = getattr(app.state, "grpc_server", None)
        if grpc_server:
            await grpc_server.stop()
            logger.info("grpc_server_stopped")
            print("✅ gRPC server stopped")
    except Exception as e:
        logger.error("grpc_server_shutdown_failed", error=str(e), exc_info=True)
        print(f"⚠️  gRPC server shutdown failed: {e}")
    
    # Close query gateway
    try:
        gateway = get_gateway()
        gateway.close()
        logger.info("query_gateway_closed")
        print("✅ Query gateway closed")
    except Exception as e:
        logger.error("query_gateway_cleanup_failed", error=str(e), exc_info=True)
        print(f"⚠️  Query gateway cleanup failed: {e}")

    # Shutdown tracing
    try:
        if settings.enable_tracing:
            tracing_manager = TracingManager.get_instance()
            tracing_manager.shutdown()
            logger.info("tracing_shutdown")
            print("✅ Tracing shutdown")
    except Exception as e:
        logger.error("tracing_shutdown_failed", error=str(e), exc_info=True)


# Create FastAPI application
app = FastAPI(
    title="IBM Bob - Repository Intelligence Agent",
    description="Repository-aware AI agent for autonomous incident response",
    version=__version__,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/api/v1/openapi.json",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.is_development else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure GZip Middleware for API performance
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Add observability middleware (order matters - last added runs first)
if settings.enable_metrics:
    app.add_middleware(MetricsMiddleware)
    logger.info("metrics_middleware_added")

if settings.enable_tracing:
    app.add_middleware(TracingMiddleware)
    logger.info("tracing_middleware_added")

app.add_middleware(LoggingMiddleware)
app.add_middleware(ErrorHandlingMiddleware)
logger.info("observability_middleware_added")


# ============================================================================
# Middleware
# ============================================================================


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """Add unique request ID to each request"""
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    
    return response


# ============================================================================
# Root Endpoints
# ============================================================================


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint"""
    return {
        "service": "IBM Bob",
        "version": __version__,
        "status": "operational",
        "docs": "/docs",
        "api": "/api/v1/bob",
    }


@app.get("/health/live")
async def liveness_check() -> JSONResponse:
    """
    Kubernetes liveness probe.
    Returns 200 if service is alive.
    """
    health_manager = HealthCheckManager.get_instance()
    result = await health_manager.liveness()
    return JSONResponse(content=result, status_code=200)


@app.get("/health/ready")
async def readiness_check() -> JSONResponse:
    """
    Kubernetes readiness probe.
    Returns 200 if service is ready to accept traffic.
    """
    from fastapi import HTTPException
    
    health_manager = HealthCheckManager.get_instance()
    result = await health_manager.readiness()
    
    if result["status"] == "unhealthy":
        raise HTTPException(status_code=503, detail=result)
    
    return JSONResponse(content=result, status_code=200)


@app.get("/health/startup")
async def startup_check() -> JSONResponse:
    """
    Kubernetes startup probe.
    Returns 200 if service has completed initialization.
    """
    from fastapi import HTTPException
    
    health_manager = HealthCheckManager.get_instance()
    result = await health_manager.startup()
    
    if result["status"] == "unhealthy":
        raise HTTPException(status_code=503, detail=result)
    
    return JSONResponse(content=result, status_code=200)


@app.get("/metrics")
async def metrics_endpoint():
    """
    Prometheus metrics endpoint.
    Returns metrics in Prometheus format.
    """
    from fastapi import Response
    
    if not settings.enable_metrics:
        return JSONResponse(
            content={"error": "Metrics disabled"},
            status_code=404
        )
    
    metrics_manager = get_metrics_manager()
    metrics_output = metrics_manager.generate_metrics()
    
    return Response(
        content=metrics_output,
        media_type=metrics_manager.get_content_type()
    )


# Legacy endpoints for backward compatibility
@app.get("/readiness")
async def readiness_check_legacy() -> JSONResponse:
    """Legacy readiness endpoint"""
    return await readiness_check()


@app.get("/liveness")
async def liveness_check_legacy() -> JSONResponse:
    """Legacy liveness endpoint"""
    return await liveness_check()


# ============================================================================
# Include API Routers
# ============================================================================

from bob.api.rest import router as api_router

app.include_router(
    api_router,
    prefix="/api/v1/bob",
    tags=["bob"],
)

print(f"✅ API router registered at /api/v1/bob")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "bob.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.is_development,
        log_level=settings.log_level.lower(),
    )

# Made with Bob
