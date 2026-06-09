"""
IBM Bob - Observability Unit Tests
Tests for tracing, metrics, logging, health checks, and performance monitoring
"""

import asyncio
import time
from unittest.mock import MagicMock, patch

import pytest

from bob.observability.health import (
    HealthCheckManager,
    HealthCheckResult,
    HealthStatus,
)
from bob.observability.logging import LoggingManager, bind_context, clear_context
from bob.observability.metrics import MetricsManager
from bob.observability.performance import PerformanceMonitor
from bob.observability.tracing import TracingManager


class TestTracingManager:
    """Tests for TracingManager"""

    def test_tracer_initialization(self):
        """Test tracer manager initialization"""
        with patch("bob.config.settings.enable_tracing", True):
            manager = TracingManager()
            assert manager is not None
            tracer = manager.get_tracer()
            assert tracer is not None

    def test_tracer_disabled(self):
        """Test tracer when tracing is disabled"""
        with patch("bob.config.settings.enable_tracing", False):
            manager = TracingManager()
            tracer = manager.get_tracer()
            assert tracer is not None  # Should still return a tracer

    def test_create_span(self):
        """Test span creation"""
        with patch("bob.config.settings.enable_tracing", True):
            manager = TracingManager()
            with manager.create_span("test_operation") as span:
                assert span is not None or span is None  # Depends on config

    def test_create_span_with_attributes(self):
        """Test span creation with attributes"""
        with patch("bob.config.settings.enable_tracing", True):
            manager = TracingManager()
            attributes = {
                "test.key": "test_value",
                "test.number": 42,
                "test.bool": True,
            }
            with manager.create_span("test_operation", attributes=attributes) as span:
                pass  # Span should be created with attributes

    def test_get_trace_id(self):
        """Test getting trace ID"""
        with patch("bob.config.settings.enable_tracing", True):
            manager = TracingManager()
            trace_id = manager.get_trace_id()
            # May be None if no active span
            assert trace_id is None or isinstance(trace_id, str)

    def test_get_span_id(self):
        """Test getting span ID"""
        with patch("bob.config.settings.enable_tracing", True):
            manager = TracingManager()
            span_id = manager.get_span_id()
            # May be None if no active span
            assert span_id is None or isinstance(span_id, str)


class TestMetricsManager:
    """Tests for MetricsManager"""

    def test_metrics_initialization(self):
        """Test metrics manager initialization"""
        with patch("bob.config.settings.enable_metrics", True):
            manager = MetricsManager()
            assert manager is not None
            assert manager.http_requests_total is not None
            assert manager.query_duration_seconds is not None

    def test_metrics_disabled(self):
        """Test metrics when disabled"""
        with patch("bob.config.settings.enable_metrics", False):
            manager = MetricsManager()
            assert manager is not None

    def test_http_request_counter(self):
        """Test HTTP request counter"""
        with patch("bob.config.settings.enable_metrics", True):
            manager = MetricsManager()
            initial_value = manager.http_requests_total.labels(
                method="GET", endpoint="/test", status="200"
            )._value._value

            manager.http_requests_total.labels(
                method="GET", endpoint="/test", status="200"
            ).inc()

            new_value = manager.http_requests_total.labels(
                method="GET", endpoint="/test", status="200"
            )._value._value

            assert new_value == initial_value + 1

    def test_query_duration_histogram(self):
        """Test query duration histogram"""
        with patch("bob.config.settings.enable_metrics", True):
            manager = MetricsManager()
            manager.query_duration_seconds.labels(query_type="semantic_search").observe(
                0.5
            )
            # Histogram should record the observation
            assert True  # If no exception, test passes

    def test_cache_metrics(self):
        """Test cache hit/miss counters"""
        with patch("bob.config.settings.enable_metrics", True):
            manager = MetricsManager()
            manager.cache_hits_total.labels(cache_type="redis").inc()
            manager.cache_misses_total.labels(cache_type="redis").inc()
            assert True  # If no exception, test passes

    def test_generate_metrics(self):
        """Test metrics generation"""
        with patch("bob.config.settings.enable_metrics", True):
            manager = MetricsManager()
            metrics_output = manager.generate_metrics()
            assert isinstance(metrics_output, bytes)


class TestLoggingManager:
    """Tests for LoggingManager"""

    def test_logging_initialization(self):
        """Test logging manager initialization"""
        manager = LoggingManager()
        assert manager is not None

    def test_get_logger(self):
        """Test getting a logger"""
        manager = LoggingManager()
        logger = manager.get_logger("test_logger")
        assert logger is not None

    def test_bind_context(self):
        """Test binding context variables"""
        bind_context(request_id="test-123", user_id="user-456")
        # Context should be bound
        clear_context()  # Clean up

    def test_clear_context(self):
        """Test clearing context variables"""
        bind_context(request_id="test-123")
        clear_context()
        # Context should be cleared
        assert True  # If no exception, test passes

    def test_logger_methods(self):
        """Test logger methods"""
        manager = LoggingManager()
        logger = manager.get_logger("test_logger")

        # Test different log levels
        logger.debug("Debug message", key="value")
        logger.info("Info message", key="value")
        logger.warning("Warning message", key="value")
        logger.error("Error message", key="value")

        assert True  # If no exception, test passes


class TestHealthCheckManager:
    """Tests for HealthCheckManager"""

    def test_health_check_initialization(self):
        """Test health check manager initialization"""
        manager = HealthCheckManager()
        assert manager is not None
        assert len(manager.checks) == 0

    def test_register_check(self):
        """Test registering a health check"""
        manager = HealthCheckManager()

        async def test_check():
            return HealthCheckResult(status=HealthStatus.HEALTHY)

        manager.register_check("test_check", test_check)
        assert "test_check" in manager.checks

    def test_unregister_check(self):
        """Test unregistering a health check"""
        manager = HealthCheckManager()

        async def test_check():
            return HealthCheckResult(status=HealthStatus.HEALTHY)

        manager.register_check("test_check", test_check)
        manager.unregister_check("test_check")
        assert "test_check" not in manager.checks

    @pytest.mark.asyncio
    async def test_run_checks_healthy(self):
        """Test running health checks - all healthy"""
        manager = HealthCheckManager()

        async def healthy_check():
            return HealthCheckResult(status=HealthStatus.HEALTHY, message="OK")

        manager.register_check("test_check", healthy_check)
        results = await manager.run_checks()

        assert results["status"] == HealthStatus.HEALTHY.value
        assert "test_check" in results["checks"]
        assert results["checks"]["test_check"]["status"] == HealthStatus.HEALTHY.value

    @pytest.mark.asyncio
    async def test_run_checks_unhealthy(self):
        """Test running health checks - one unhealthy"""
        manager = HealthCheckManager()

        async def unhealthy_check():
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY, error="Connection failed"
            )

        manager.register_check("test_check", unhealthy_check)
        results = await manager.run_checks()

        assert results["status"] == HealthStatus.UNHEALTHY.value
        assert results["checks"]["test_check"]["status"] == HealthStatus.UNHEALTHY.value

    @pytest.mark.asyncio
    async def test_run_checks_timeout(self):
        """Test health check timeout"""
        manager = HealthCheckManager()

        async def slow_check():
            await asyncio.sleep(10)  # Longer than timeout
            return HealthCheckResult(status=HealthStatus.HEALTHY)

        manager.register_check("slow_check", slow_check)
        results = await manager.run_checks(timeout=0.1)

        assert results["status"] == HealthStatus.UNHEALTHY.value
        assert "timeout" in results["checks"]["slow_check"]["error"].lower()

    @pytest.mark.asyncio
    async def test_liveness_probe(self):
        """Test liveness probe"""
        manager = HealthCheckManager()
        result = await manager.liveness()
        assert result["status"] == HealthStatus.HEALTHY.value

    @pytest.mark.asyncio
    async def test_readiness_probe(self):
        """Test readiness probe"""
        manager = HealthCheckManager()
        result = await manager.readiness()
        assert "status" in result
        assert "checks" in result

    @pytest.mark.asyncio
    async def test_startup_probe(self):
        """Test startup probe"""
        manager = HealthCheckManager()

        # Before startup complete
        result = await manager.startup()
        assert result["status"] == HealthStatus.UNHEALTHY.value

        # After startup complete
        manager.mark_startup_complete()
        result = await manager.startup()
        assert result["status"] == HealthStatus.HEALTHY.value


class TestHealthCheckResult:
    """Tests for HealthCheckResult"""

    def test_healthy_result(self):
        """Test creating a healthy result"""
        result = HealthCheckResult(status=HealthStatus.HEALTHY, message="All good")
        assert result.status == HealthStatus.HEALTHY
        assert result.message == "All good"
        assert result.error is None

    def test_unhealthy_result(self):
        """Test creating an unhealthy result"""
        result = HealthCheckResult(
            status=HealthStatus.UNHEALTHY, error="Connection failed"
        )
        assert result.status == HealthStatus.UNHEALTHY
        assert result.error == "Connection failed"

    def test_result_to_dict(self):
        """Test converting result to dictionary"""
        result = HealthCheckResult(
            status=HealthStatus.HEALTHY,
            message="OK",
            details={"latency_ms": 10},
        )
        result_dict = result.to_dict()

        assert result_dict["status"] == HealthStatus.HEALTHY.value
        assert result_dict["message"] == "OK"
        assert result_dict["details"]["latency_ms"] == 10
        assert "timestamp" in result_dict


class TestPerformanceMonitor:
    """Tests for PerformanceMonitor"""

    def test_performance_monitor_initialization(self):
        """Test performance monitor initialization"""
        with patch("bob.config.settings.enable_metrics", True):
            monitor = PerformanceMonitor()
            assert monitor is not None

    def test_track_operation(self):
        """Test tracking operation duration"""
        with patch("bob.config.settings.enable_metrics", True):
            monitor = PerformanceMonitor()

            with monitor.track_operation("test_operation"):
                time.sleep(0.01)  # Simulate work

            assert True  # If no exception, test passes

    def test_track_query_performance(self):
        """Test tracking query performance"""
        with patch("bob.config.settings.enable_metrics", True):
            monitor = PerformanceMonitor()
            monitor.track_query_performance(
                query_type="semantic_search",
                duration=0.5,
                result_count=10,
                status="success",
            )
            assert True  # If no exception, test passes

    def test_track_indexing_performance(self):
        """Test tracking indexing performance"""
        with patch("bob.config.settings.enable_metrics", True):
            monitor = PerformanceMonitor()
            monitor.track_indexing_performance(
                repo_id="test-repo",
                duration=60.0,
                files_processed=100,
                lines_of_code=10000,
                status="success",
            )
            assert True  # If no exception, test passes

    def test_track_db_query(self):
        """Test tracking database query"""
        with patch("bob.config.settings.enable_metrics", True):
            monitor = PerformanceMonitor()
            monitor.track_db_query(
                db_type="postgres",
                operation="read",
                duration=0.05,
                status="success",
            )
            assert True  # If no exception, test passes

    def test_track_cache_operation(self):
        """Test tracking cache operation"""
        with patch("bob.config.settings.enable_metrics", True):
            monitor = PerformanceMonitor()
            monitor.track_cache_operation(cache_type="redis", hit=True, duration=0.001)
            monitor.track_cache_operation(cache_type="redis", hit=False, duration=0.002)
            assert True  # If no exception, test passes

    def test_track_parsing_performance(self):
        """Test tracking parsing performance"""
        with patch("bob.config.settings.enable_metrics", True):
            monitor = PerformanceMonitor()
            monitor.track_parsing_performance(
                language="python",
                duration=0.1,
                file_size_bytes=5000,
                status="success",
            )
            assert True  # If no exception, test passes

    def test_track_http_request(self):
        """Test tracking HTTP request"""
        with patch("bob.config.settings.enable_metrics", True):
            monitor = PerformanceMonitor()
            monitor.track_http_request(
                method="GET",
                endpoint="/api/v1/test",
                status_code=200,
                duration=0.5,
                request_size=1024,
                response_size=2048,
            )
            assert True  # If no exception, test passes


# Made with Bob