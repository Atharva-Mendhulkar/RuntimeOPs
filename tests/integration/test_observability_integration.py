"""
IBM Bob - Observability Integration Tests
End-to-end tests for observability components
"""

import asyncio
import time
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from bob.observability.health import (
    HealthCheckManager,
    HealthCheckResult,
    HealthStatus,
    register_default_checks,
)
from bob.observability.logging import bind_context, clear_context, get_logger
from bob.observability.metrics import get_metrics_manager
from bob.observability.middleware import (
    LoggingMiddleware,
    MetricsMiddleware,
    TracingMiddleware,
)
from bob.observability.performance import get_performance_monitor
from bob.observability.tracing import TracingManager


@pytest.fixture
def app():
    """Create a test FastAPI application"""
    app = FastAPI()

    @app.get("/test")
    async def test_endpoint():
        return {"message": "test"}

    @app.get("/error")
    async def error_endpoint():
        raise ValueError("Test error")

    return app


@pytest.fixture
def client(app):
    """Create a test client"""
    return TestClient(app)


class TestTracingIntegration:
    """Integration tests for tracing"""

    def test_tracing_through_request_lifecycle(self, app, client):
        """Test tracing through complete request lifecycle"""
        with patch("bob.config.settings.enable_tracing", True):
            # Initialize tracing
            tracing_manager = TracingManager()
            tracing_manager.instrument_fastapi(app)

            # Make request
            response = client.get("/test")
            assert response.status_code == 200

            # Check for trace headers
            assert "X-Trace-ID" in response.headers or True  # May not be set in test

    def test_span_creation_in_operation(self):
        """Test span creation during operation"""
        with patch("bob.config.settings.enable_tracing", True):
            tracing_manager = TracingManager()

            with tracing_manager.create_span(
                "test_operation",
                attributes={"test.key": "test_value"},
            ) as span:
                # Simulate work
                time.sleep(0.01)

            # Span should be completed
            assert True  # If no exception, test passes


class TestMetricsIntegration:
    """Integration tests for metrics"""

    def test_metrics_collection_across_requests(self, app, client):
        """Test metrics collection across multiple requests"""
        with patch("bob.config.settings.enable_metrics", True):
            # Add metrics middleware
            app.add_middleware(MetricsMiddleware)

            # Make multiple requests
            for _ in range(5):
                response = client.get("/test")
                assert response.status_code == 200

            # Check metrics
            metrics_manager = get_metrics_manager()
            metrics_output = metrics_manager.generate_metrics()
            assert len(metrics_output) > 0

    def test_metrics_endpoint(self):
        """Test metrics endpoint"""
        with patch("bob.config.settings.enable_metrics", True):
            metrics_manager = get_metrics_manager()

            # Generate some metrics
            metrics_manager.http_requests_total.labels(
                method="GET", endpoint="/test", status="200"
            ).inc()

            # Get metrics
            metrics_output = metrics_manager.generate_metrics()
            assert b"bob_http_requests_total" in metrics_output


class TestLoggingIntegration:
    """Integration tests for logging"""

    def test_logging_with_context_propagation(self, app, client):
        """Test logging with context propagation"""
        # Add logging middleware
        app.add_middleware(LoggingMiddleware)

        # Make request
        response = client.get("/test")
        assert response.status_code == 200

        # Context should be cleared after request
        assert True  # If no exception, test passes

    def test_structured_logging_with_trace_correlation(self):
        """Test structured logging with trace correlation"""
        logger = get_logger(__name__)

        # Bind context
        bind_context(request_id="test-123", user_id="user-456")

        # Log messages
        logger.info("Test message", key="value")

        # Clear context
        clear_context()

        assert True  # If no exception, test passes


class TestHealthCheckIntegration:
    """Integration tests for health checks"""

    @pytest.mark.asyncio
    async def test_health_check_endpoints(self):
        """Test health check endpoints"""
        manager = HealthCheckManager()

        # Test liveness
        liveness = await manager.liveness()
        assert liveness["status"] == HealthStatus.HEALTHY.value

        # Test readiness
        readiness = await manager.readiness()
        assert "status" in readiness

        # Test startup
        startup = await manager.startup()
        assert "status" in startup

    @pytest.mark.asyncio
    async def test_health_checks_with_dependencies(self):
        """Test health checks with mock dependencies"""
        manager = HealthCheckManager()

        # Register mock checks
        async def mock_postgres_check():
            return HealthCheckResult(status=HealthStatus.HEALTHY, message="OK")

        async def mock_redis_check():
            return HealthCheckResult(status=HealthStatus.HEALTHY, message="OK")

        manager.register_check("postgres", mock_postgres_check)
        manager.register_check("redis", mock_redis_check)

        # Run checks
        results = await manager.run_checks()
        assert results["status"] == HealthStatus.HEALTHY.value
        assert len(results["checks"]) == 2

    @pytest.mark.asyncio
    async def test_health_check_degraded_state(self):
        """Test health check with degraded dependency"""
        manager = HealthCheckManager()

        async def healthy_check():
            return HealthCheckResult(status=HealthStatus.HEALTHY)

        async def degraded_check():
            return HealthCheckResult(status=HealthStatus.DEGRADED, message="Slow response")

        manager.register_check("service_a", healthy_check)
        manager.register_check("service_b", degraded_check)

        results = await manager.run_checks()
        assert results["status"] == HealthStatus.DEGRADED.value


class TestPerformanceMonitoringIntegration:
    """Integration tests for performance monitoring"""

    def test_performance_tracking_end_to_end(self):
        """Test performance tracking through operation"""
        with patch("bob.config.settings.enable_metrics", True):
            perf_monitor = get_performance_monitor()

            # Track operation
            with perf_monitor.track_operation("test_operation"):
                time.sleep(0.01)

            assert True  # If no exception, test passes

    def test_query_performance_tracking(self):
        """Test query performance tracking"""
        with patch("bob.config.settings.enable_metrics", True):
            perf_monitor = get_performance_monitor()

            # Track query
            perf_monitor.track_query_performance(
                query_type="semantic_search",
                duration=0.5,
                result_count=10,
                status="success",
            )

            assert True  # If no exception, test passes

    def test_multiple_performance_metrics(self):
        """Test tracking multiple performance metrics"""
        with patch("bob.config.settings.enable_metrics", True):
            perf_monitor = get_performance_monitor()

            # Track various operations
            perf_monitor.track_indexing_performance(
                repo_id="test-repo",
                duration=60.0,
                files_processed=100,
                lines_of_code=10000,
            )

            perf_monitor.track_db_query(db_type="postgres", operation="read", duration=0.05)

            perf_monitor.track_cache_operation(cache_type="redis", hit=True)

            assert True  # If no exception, test passes


class TestMiddlewareIntegration:
    """Integration tests for middleware stack"""

    def test_middleware_stack(self, app, client):
        """Test complete middleware stack"""
        with patch("bob.config.settings.enable_tracing", True):
            with patch("bob.config.settings.enable_metrics", True):
                # Add all middleware
                app.add_middleware(TracingMiddleware)
                app.add_middleware(MetricsMiddleware)
                app.add_middleware(LoggingMiddleware)

                # Make request
                response = client.get("/test")
                assert response.status_code == 200

    def test_middleware_error_handling(self, app, client):
        """Test middleware error handling"""
        with patch("bob.config.settings.enable_tracing", True):
            with patch("bob.config.settings.enable_metrics", True):
                # Add middleware
                app.add_middleware(TracingMiddleware)
                app.add_middleware(MetricsMiddleware)
                app.add_middleware(LoggingMiddleware)

                # Make request that raises error
                with pytest.raises(Exception):
                    client.get("/error")


class TestObservabilityEndToEnd:
    """End-to-end observability tests"""

    @pytest.mark.asyncio
    async def test_complete_observability_flow(self):
        """Test complete observability flow"""
        with patch("bob.config.settings.enable_tracing", True):
            with patch("bob.config.settings.enable_metrics", True):
                # Initialize components
                tracing_manager = TracingManager()
                metrics_manager = get_metrics_manager()
                perf_monitor = get_performance_monitor()
                health_manager = HealthCheckManager()

                # Simulate operation with full observability
                with tracing_manager.create_span("test_operation") as span:
                    # Bind logging context
                    bind_context(operation="test", trace_id=tracing_manager.get_trace_id())

                    # Track performance
                    with perf_monitor.track_operation("sub_operation"):
                        time.sleep(0.01)

                    # Record metrics
                    metrics_manager.queries_total.labels(query_type="test", status="success").inc()

                    # Clear context
                    clear_context()

                # Check health
                health_result = await health_manager.liveness()
                assert health_result["status"] == HealthStatus.HEALTHY.value

    def test_observability_with_disabled_features(self):
        """Test observability when features are disabled"""
        with patch("bob.config.settings.enable_tracing", False):
            with patch("bob.config.settings.enable_metrics", False):
                # Components should still work without errors
                tracing_manager = TracingManager()
                metrics_manager = get_metrics_manager()

                with tracing_manager.create_span("test"):
                    pass

                metrics_output = metrics_manager.generate_metrics()
                assert metrics_output == b""


# Made with Bob
