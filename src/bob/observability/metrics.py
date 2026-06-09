"""
IBM Bob - Prometheus Metrics
Metrics collection and export for monitoring system health and performance
"""

from typing import Optional

from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    Info,
    CollectorRegistry,
    generate_latest,
    CONTENT_TYPE_LATEST,
)

from bob.config import settings


class MetricsManager:
    """
    Manages Prometheus metrics collection.
    Provides counters, histograms, and gauges for monitoring Bob's operations.
    """

    _instance: Optional["MetricsManager"] = None
    _registry: Optional[CollectorRegistry] = None

    def __init__(self):
        """Initialize Prometheus metrics"""
        if not settings.enable_metrics:
            return

        # Create custom registry
        self._registry = CollectorRegistry()

        # ============================================================================
        # HTTP Request Metrics
        # ============================================================================

        self.http_requests_total = Counter(
            "bob_http_requests_total",
            "Total HTTP requests",
            ["method", "endpoint", "status"],
            registry=self._registry,
        )

        self.http_request_duration_seconds = Histogram(
            "bob_http_request_duration_seconds",
            "HTTP request duration in seconds",
            ["method", "endpoint"],
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
            registry=self._registry,
        )

        self.http_request_size_bytes = Histogram(
            "bob_http_request_size_bytes",
            "HTTP request size in bytes",
            ["method", "endpoint"],
            registry=self._registry,
        )

        self.http_response_size_bytes = Histogram(
            "bob_http_response_size_bytes",
            "HTTP response size in bytes",
            ["method", "endpoint"],
            registry=self._registry,
        )

        # ============================================================================
        # Repository Metrics
        # ============================================================================

        self.repositories_indexed_total = Counter(
            "bob_repositories_indexed_total",
            "Total repositories indexed",
            ["status"],
            registry=self._registry,
        )

        self.repository_index_duration_seconds = Histogram(
            "bob_repository_index_duration_seconds",
            "Repository indexing duration in seconds",
            buckets=(1, 5, 10, 30, 60, 120, 300, 600, 1200, 1800),
            registry=self._registry,
        )

        self.repository_files_processed_total = Counter(
            "bob_repository_files_processed_total",
            "Total files processed during indexing",
            ["language"],
            registry=self._registry,
        )

        self.repository_lines_of_code_total = Counter(
            "bob_repository_lines_of_code_total",
            "Total lines of code indexed",
            ["language"],
            registry=self._registry,
        )

        self.repositories_active = Gauge(
            "bob_repositories_active",
            "Number of active repositories",
            registry=self._registry,
        )

        # ============================================================================
        # Query Metrics
        # ============================================================================

        self.queries_total = Counter(
            "bob_queries_total",
            "Total queries executed",
            ["query_type", "status"],
            registry=self._registry,
        )

        self.query_duration_seconds = Histogram(
            "bob_query_duration_seconds",
            "Query execution duration in seconds",
            ["query_type"],
            buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
            registry=self._registry,
        )

        self.query_results_count = Histogram(
            "bob_query_results_count",
            "Number of results returned by query",
            ["query_type"],
            buckets=(1, 5, 10, 25, 50, 100, 250, 500, 1000),
            registry=self._registry,
        )

        # ============================================================================
        # Cache Metrics
        # ============================================================================

        self.cache_hits_total = Counter(
            "bob_cache_hits_total",
            "Total cache hits",
            ["cache_type"],
            registry=self._registry,
        )

        self.cache_misses_total = Counter(
            "bob_cache_misses_total",
            "Total cache misses",
            ["cache_type"],
            registry=self._registry,
        )

        self.cache_size_bytes = Gauge(
            "bob_cache_size_bytes",
            "Cache size in bytes",
            ["cache_type"],
            registry=self._registry,
        )

        self.cache_evictions_total = Counter(
            "bob_cache_evictions_total",
            "Total cache evictions",
            ["cache_type"],
            registry=self._registry,
        )

        # ============================================================================
        # Database Metrics
        # ============================================================================

        self.db_connections_active = Gauge(
            "bob_db_connections_active",
            "Active database connections",
            ["db_type"],
            registry=self._registry,
        )

        self.db_connections_idle = Gauge(
            "bob_db_connections_idle",
            "Idle database connections",
            ["db_type"],
            registry=self._registry,
        )

        self.db_query_duration_seconds = Histogram(
            "bob_db_query_duration_seconds",
            "Database query duration in seconds",
            ["db_type", "operation"],
            buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
            registry=self._registry,
        )

        self.db_queries_total = Counter(
            "bob_db_queries_total",
            "Total database queries",
            ["db_type", "operation", "status"],
            registry=self._registry,
        )

        # ============================================================================
        # Vector Store Metrics
        # ============================================================================

        self.vector_embeddings_generated_total = Counter(
            "bob_vector_embeddings_generated_total",
            "Total vector embeddings generated",
            ["model"],
            registry=self._registry,
        )

        self.vector_search_duration_seconds = Histogram(
            "bob_vector_search_duration_seconds",
            "Vector search duration in seconds",
            buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
            registry=self._registry,
        )

        self.vector_store_objects_total = Gauge(
            "bob_vector_store_objects_total",
            "Total objects in vector store",
            registry=self._registry,
        )

        # ============================================================================
        # Graph Metrics
        # ============================================================================

        self.graph_nodes_total = Gauge(
            "bob_graph_nodes_total",
            "Total nodes in graph",
            ["node_type"],
            registry=self._registry,
        )

        self.graph_edges_total = Gauge(
            "bob_graph_edges_total",
            "Total edges in graph",
            ["edge_type"],
            registry=self._registry,
        )

        self.graph_traversal_duration_seconds = Histogram(
            "bob_graph_traversal_duration_seconds",
            "Graph traversal duration in seconds",
            ["traversal_type"],
            buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
            registry=self._registry,
        )

        # ============================================================================
        # Parsing Metrics
        # ============================================================================

        self.files_parsed_total = Counter(
            "bob_files_parsed_total",
            "Total files parsed",
            ["language", "status"],
            registry=self._registry,
        )

        self.parse_duration_seconds = Histogram(
            "bob_parse_duration_seconds",
            "File parsing duration in seconds",
            ["language"],
            buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
            registry=self._registry,
        )

        self.parse_errors_total = Counter(
            "bob_parse_errors_total",
            "Total parsing errors",
            ["language", "error_type"],
            registry=self._registry,
        )

        # ============================================================================
        # System Metrics
        # ============================================================================

        self.system_info = Info(
            "bob_system",
            "System information",
            registry=self._registry,
        )

        # Set system info
        self.system_info.info(
            {
                "version": "1.0.0",
                "environment": settings.environment,
                "python_version": "3.11+",
            }
        )

        self.errors_total = Counter(
            "bob_errors_total",
            "Total errors",
            ["error_type", "component"],
            registry=self._registry,
        )

        self.background_jobs_active = Gauge(
            "bob_background_jobs_active",
            "Active background jobs",
            ["job_type"],
            registry=self._registry,
        )

        self.background_jobs_completed_total = Counter(
            "bob_background_jobs_completed_total",
            "Total completed background jobs",
            ["job_type", "status"],
            registry=self._registry,
        )

    def get_registry(self) -> Optional[CollectorRegistry]:
        """
        Get Prometheus registry.

        Returns:
            CollectorRegistry instance or None
        """
        return self._registry

    def generate_metrics(self) -> bytes:
        """
        Generate metrics in Prometheus format.

        Returns:
            Metrics as bytes
        """
        if not settings.enable_metrics or not self._registry:
            return b""
        return generate_latest(self._registry)

    def get_content_type(self) -> str:
        """
        Get content type for metrics endpoint.

        Returns:
            Content type string
        """
        return CONTENT_TYPE_LATEST

    @classmethod
    def get_instance(cls) -> "MetricsManager":
        """
        Get singleton instance of MetricsManager.

        Returns:
            MetricsManager instance
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance


# Convenience function
def get_metrics_manager() -> MetricsManager:
    """Get MetricsManager instance"""
    return MetricsManager.get_instance()


# Made with Bob