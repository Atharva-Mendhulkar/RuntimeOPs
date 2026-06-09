"""
IBM Bob - Observability Middleware
FastAPI middleware for tracing, metrics, and logging
"""

import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from bob.observability.logging import bind_context, clear_context, get_logger
from bob.observability.metrics import get_metrics_manager
from bob.observability.performance import get_performance_monitor
from bob.observability.tracing import (
    TracingManager,
    get_span_id,
    get_trace_id,
    set_span_error,
)

logger = get_logger(__name__)


class TracingMiddleware(BaseHTTPMiddleware):
    """
    Middleware for distributed tracing.
    Automatically creates spans for all HTTP requests.
    """

    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.tracing_manager = TracingManager.get_instance()

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Add tracing to all requests.

        Args:
            request: FastAPI request
            call_next: Next middleware/handler

        Returns:
            Response
        """
        # Create span for request
        with self.tracing_manager.create_span(
            f"{request.method} {request.url.path}",
            attributes={
                "http.method": request.method,
                "http.url": str(request.url),
                "http.scheme": request.url.scheme,
                "http.host": request.url.hostname or "",
                "http.target": request.url.path,
                "http.user_agent": request.headers.get("user-agent", ""),
                "http.client_ip": request.client.host if request.client else "",
            },
        ) as span:
            try:
                # Process request
                response = await call_next(request)

                # Add response attributes to span
                if span:
                    span.set_attribute("http.status_code", response.status_code)

                # Add trace headers to response
                trace_id = get_trace_id()
                span_id = get_span_id()
                if trace_id:
                    response.headers["X-Trace-ID"] = trace_id
                if span_id:
                    response.headers["X-Span-ID"] = span_id

                return response

            except Exception as e:
                # Record exception in span
                if span:
                    set_span_error(span, e)
                raise


class MetricsMiddleware(BaseHTTPMiddleware):
    """
    Middleware for collecting metrics.
    Records request counts, durations, and sizes.
    """

    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.metrics = get_metrics_manager()
        self.perf_monitor = get_performance_monitor()

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Collect metrics for all requests.

        Args:
            request: FastAPI request
            call_next: Next middleware/handler

        Returns:
            Response
        """
        start_time = time.time()

        # Get request size
        request_size = int(request.headers.get("content-length", 0))

        try:
            # Process request
            response = await call_next(request)

            # Calculate duration
            duration = time.time() - start_time

            # Get response size
            response_size = int(response.headers.get("content-length", 0))

            # Track metrics
            self.perf_monitor.track_http_request(
                method=request.method,
                endpoint=request.url.path,
                status_code=response.status_code,
                duration=duration,
                request_size=request_size if request_size > 0 else None,
                response_size=response_size if response_size > 0 else None,
            )

            return response

        except Exception as e:
            # Track error
            duration = time.time() - start_time
            self.perf_monitor.track_http_request(
                method=request.method,
                endpoint=request.url.path,
                status_code=500,
                duration=duration,
                request_size=request_size if request_size > 0 else None,
            )
            raise


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware for structured logging.
    Adds request context to all log messages.
    """

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Log all requests with context.

        Args:
            request: FastAPI request
            call_next: Next middleware/handler

        Returns:
            Response
        """
        # Get request ID (should be set by earlier middleware)
        request_id = getattr(request.state, "request_id", None)

        # Get trace context
        trace_id = get_trace_id()
        span_id = get_span_id()

        # Bind context for all log messages in this request
        bind_context(
            request_id=request_id,
            trace_id=trace_id,
            span_id=span_id,
            method=request.method,
            path=request.url.path,
            client_ip=request.client.host if request.client else None,
        )

        try:
            # Log request start
            logger.info(
                "request_started",
                user_agent=request.headers.get("user-agent", ""),
            )

            start_time = time.time()

            # Process request
            response = await call_next(request)

            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000

            # Log request completion
            logger.info(
                "request_completed",
                status_code=response.status_code,
                duration_ms=duration_ms,
            )

            return response

        except Exception as e:
            # Log error
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                "request_failed",
                error=str(e),
                error_type=type(e).__name__,
                duration_ms=duration_ms,
                exc_info=True,
            )
            raise

        finally:
            # Clear context after request
            clear_context()


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """
    Middleware for error handling and reporting.
    Catches unhandled exceptions and reports them to observability systems.
    """

    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.metrics = get_metrics_manager()

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Handle errors and report to observability systems.

        Args:
            request: FastAPI request
            call_next: Next middleware/handler

        Returns:
            Response
        """
        try:
            return await call_next(request)

        except Exception as e:
            # Record error metric
            self.metrics.errors_total.labels(
                error_type=type(e).__name__,
                component="api",
            ).inc()

            # Log error with full context
            logger.error(
                "unhandled_exception",
                error=str(e),
                error_type=type(e).__name__,
                method=request.method,
                path=request.url.path,
                exc_info=True,
            )

            # Re-raise to let FastAPI handle the response
            raise


# Made with Bob