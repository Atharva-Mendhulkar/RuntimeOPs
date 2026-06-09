"""
IBM Bob - Performance Monitoring
Performance tracking and profiling utilities for monitoring operation durations
"""

import time
from contextlib import contextmanager
from typing import Any, Dict, Optional

from bob.observability.logging import get_logger
from bob.observability.metrics import get_metrics_manager
from bob.observability.tracing import create_span, get_trace_id

logger = get_logger(__name__)


class PerformanceMonitor:
    """
    Monitors and tracks performance of operations.
    Integrates with metrics and tracing for comprehensive observability.
    """

    _instance: Optional["PerformanceMonitor"] = None

    def __init__(self):
        """Initialize performance monitor"""
        self.metrics = get_metrics_manager()

    @contextmanager
    def track_operation(
        self,
        operation_name: str,
        labels: Optional[Dict[str, str]] = None,
        log_threshold_ms: float = 1000.0,
    ):
        """
        Context manager to track operation duration.

        Args:
            operation_name: Name of the operation
            labels: Optional labels for metrics
            log_threshold_ms: Log warning if duration exceeds this threshold

        Yields:
            None
        """
        start_time = time.time()
        trace_id = get_trace_id()

        # Create span for tracing
        with create_span(
            operation_name,
            attributes={"operation.name": operation_name, **(labels or {})},
        ):
            try:
                yield
            finally:
                duration = time.time() - start_time
                duration_ms = duration * 1000

                # Log if exceeds threshold
                if duration_ms > log_threshold_ms:
                    logger.warning(
                        "slow_operation",
                        operation=operation_name,
                        duration_ms=duration_ms,
                        threshold_ms=log_threshold_ms,
                        trace_id=trace_id,
                        **(labels or {}),
                    )
                else:
                    logger.debug(
                        "operation_completed",
                        operation=operation_name,
                        duration_ms=duration_ms,
                        trace_id=trace_id,
                        **(labels or {}),
                    )

    def track_query_performance(
        self,
        query_type: str,
        duration: float,
        result_count: int,
        status: str = "success",
    ):
        """
        Track query performance metrics.

        Args:
            query_type: Type of query (semantic_search, graph_traversal, etc.)
            duration: Query duration in seconds
            result_count: Number of results returned
            status: Query status (success, error, timeout)
        """
        # Record metrics
        self.metrics.query_duration_seconds.labels(query_type=query_type).observe(
            duration
        )
        self.metrics.queries_total.labels(
            query_type=query_type, status=status
        ).inc()
        self.metrics.query_results_count.labels(query_type=query_type).observe(
            result_count
        )

        # Log query performance
        logger.info(
            "query_performance",
            query_type=query_type,
            duration_ms=duration * 1000,
            result_count=result_count,
            status=status,
            trace_id=get_trace_id(),
        )

    def track_indexing_performance(
        self,
        repo_id: str,
        duration: float,
        files_processed: int,
        lines_of_code: int,
        status: str = "success",
    ):
        """
        Track repository indexing performance.

        Args:
            repo_id: Repository identifier
            duration: Indexing duration in seconds
            files_processed: Number of files processed
            lines_of_code: Total lines of code indexed
            status: Indexing status (success, error, timeout)
        """
        # Record metrics
        self.metrics.repository_index_duration_seconds.observe(duration)
        self.metrics.repositories_indexed_total.labels(status=status).inc()

        # Log indexing performance
        logger.info(
            "indexing_performance",
            repo_id=repo_id,
            duration_ms=duration * 1000,
            files_processed=files_processed,
            lines_of_code=lines_of_code,
            throughput_kloc_per_min=(lines_of_code / 1000) / (duration / 60),
            status=status,
            trace_id=get_trace_id(),
        )

    def track_db_query(
        self,
        db_type: str,
        operation: str,
        duration: float,
        status: str = "success",
    ):
        """
        Track database query performance.

        Args:
            db_type: Database type (postgres, neo4j, redis, weaviate)
            operation: Operation type (read, write, delete, etc.)
            duration: Query duration in seconds
            status: Query status (success, error)
        """
        # Record metrics
        self.metrics.db_query_duration_seconds.labels(
            db_type=db_type, operation=operation
        ).observe(duration)
        self.metrics.db_queries_total.labels(
            db_type=db_type, operation=operation, status=status
        ).inc()

        # Log slow queries
        if duration > 1.0:  # Log queries slower than 1 second
            logger.warning(
                "slow_db_query",
                db_type=db_type,
                operation=operation,
                duration_ms=duration * 1000,
                status=status,
                trace_id=get_trace_id(),
            )

    def track_cache_operation(
        self,
        cache_type: str,
        hit: bool,
        duration: Optional[float] = None,
    ):
        """
        Track cache operation.

        Args:
            cache_type: Cache type (redis, memory, etc.)
            hit: Whether cache hit or miss
            duration: Optional operation duration in seconds
        """
        if hit:
            self.metrics.cache_hits_total.labels(cache_type=cache_type).inc()
        else:
            self.metrics.cache_misses_total.labels(cache_type=cache_type).inc()

        logger.debug(
            "cache_operation",
            cache_type=cache_type,
            hit=hit,
            duration_ms=duration * 1000 if duration else None,
            trace_id=get_trace_id(),
        )

    def track_parsing_performance(
        self,
        language: str,
        duration: float,
        file_size_bytes: int,
        status: str = "success",
    ):
        """
        Track file parsing performance.

        Args:
            language: Programming language
            duration: Parsing duration in seconds
            file_size_bytes: File size in bytes
            status: Parsing status (success, error)
        """
        # Record metrics
        self.metrics.parse_duration_seconds.labels(language=language).observe(
            duration
        )
        self.metrics.files_parsed_total.labels(
            language=language, status=status
        ).inc()

        # Log slow parsing
        if duration > 0.5:  # Log parsing slower than 500ms
            logger.warning(
                "slow_parsing",
                language=language,
                duration_ms=duration * 1000,
                file_size_bytes=file_size_bytes,
                status=status,
                trace_id=get_trace_id(),
            )

    def track_http_request(
        self,
        method: str,
        endpoint: str,
        status_code: int,
        duration: float,
        request_size: Optional[int] = None,
        response_size: Optional[int] = None,
    ):
        """
        Track HTTP request performance.

        Args:
            method: HTTP method
            endpoint: Request endpoint
            status_code: Response status code
            duration: Request duration in seconds
            request_size: Optional request size in bytes
            response_size: Optional response size in bytes
        """
        # Record metrics
        self.metrics.http_requests_total.labels(
            method=method, endpoint=endpoint, status=str(status_code)
        ).inc()
        self.metrics.http_request_duration_seconds.labels(
            method=method, endpoint=endpoint
        ).observe(duration)

        if request_size is not None:
            self.metrics.http_request_size_bytes.labels(
                method=method, endpoint=endpoint
            ).observe(request_size)

        if response_size is not None:
            self.metrics.http_response_size_bytes.labels(
                method=method, endpoint=endpoint
            ).observe(response_size)

        # Log slow requests
        if duration > 5.0:  # Log requests slower than 5 seconds
            logger.warning(
                "slow_http_request",
                method=method,
                endpoint=endpoint,
                status_code=status_code,
                duration_ms=duration * 1000,
                trace_id=get_trace_id(),
            )

    @classmethod
    def get_instance(cls) -> "PerformanceMonitor":
        """
        Get singleton instance of PerformanceMonitor.

        Returns:
            PerformanceMonitor instance
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance


# Convenience functions
def get_performance_monitor() -> PerformanceMonitor:
    """Get PerformanceMonitor instance"""
    return PerformanceMonitor.get_instance()


def track_operation(
    operation_name: str,
    labels: Optional[Dict[str, str]] = None,
    log_threshold_ms: float = 1000.0,
):
    """Track operation duration"""
    return PerformanceMonitor.get_instance().track_operation(
        operation_name, labels, log_threshold_ms
    )


# Made with Bob