"""
IBM Bob - Observability Configuration
Configuration settings for observability components
"""

from typing import Literal, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ObservabilitySettings(BaseSettings):
    """
    Observability configuration settings.
    Extends the main application settings with observability-specific options.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_prefix="BOB_",
    )

    # ============================================================================
    # Tracing Configuration
    # ============================================================================

    tracing_enabled: bool = Field(
        default=True,
        description="Enable distributed tracing with OpenTelemetry",
    )

    tracing_exporter: Literal["otlp", "jaeger", "zipkin", "console"] = Field(
        default="otlp",
        description="Tracing exporter type",
    )

    tracing_endpoint: str = Field(
        default="http://localhost:4317",
        description="OTLP exporter endpoint (gRPC)",
    )

    tracing_sample_rate: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Trace sampling rate (0.0 to 1.0)",
    )

    tracing_service_name: str = Field(
        default="bob-repository-intelligence",
        description="Service name for tracing",
    )

    # ============================================================================
    # Metrics Configuration
    # ============================================================================

    metrics_enabled: bool = Field(
        default=True,
        description="Enable Prometheus metrics collection",
    )

    metrics_port: int = Field(
        default=9090,
        description="Port for Prometheus metrics endpoint",
    )

    metrics_path: str = Field(
        default="/metrics",
        description="Path for Prometheus metrics endpoint",
    )

    # ============================================================================
    # Logging Configuration
    # ============================================================================

    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )

    log_format: Literal["json", "text"] = Field(
        default="json",
        description="Log output format",
    )

    log_include_trace_id: bool = Field(
        default=True,
        description="Include trace ID in log messages",
    )

    log_include_span_id: bool = Field(
        default=True,
        description="Include span ID in log messages",
    )

    # ============================================================================
    # Health Check Configuration
    # ============================================================================

    health_check_enabled: bool = Field(
        default=True,
        description="Enable health check endpoints",
    )

    health_check_interval: int = Field(
        default=30,
        description="Health check interval in seconds",
    )

    health_check_timeout: float = Field(
        default=5.0,
        description="Health check timeout in seconds",
    )

    # ============================================================================
    # Performance Monitoring Configuration
    # ============================================================================

    perf_monitoring_enabled: bool = Field(
        default=True,
        description="Enable performance monitoring",
    )

    slow_query_threshold_ms: float = Field(
        default=1000.0,
        description="Threshold for logging slow queries (milliseconds)",
    )

    slow_request_threshold_ms: float = Field(
        default=5000.0,
        description="Threshold for logging slow HTTP requests (milliseconds)",
    )

    slow_parsing_threshold_ms: float = Field(
        default=500.0,
        description="Threshold for logging slow file parsing (milliseconds)",
    )

    # ============================================================================
    # Alert Configuration
    # ============================================================================

    alerting_enabled: bool = Field(
        default=True,
        description="Enable alerting",
    )

    alert_manager_url: Optional[str] = Field(
        default=None,
        description="Prometheus AlertManager URL",
    )

    # ============================================================================
    # Dashboard Configuration
    # ============================================================================

    grafana_url: Optional[str] = Field(
        default="http://localhost:3000",
        description="Grafana dashboard URL",
    )

    grafana_api_key: Optional[str] = Field(
        default=None,
        description="Grafana API key for dashboard provisioning",
    )

    # ============================================================================
    # Feature Flags
    # ============================================================================

    enable_request_logging: bool = Field(
        default=True,
        description="Enable HTTP request logging",
    )

    enable_db_query_logging: bool = Field(
        default=True,
        description="Enable database query logging",
    )

    enable_cache_metrics: bool = Field(
        default=True,
        description="Enable cache hit/miss metrics",
    )

    enable_error_tracking: bool = Field(
        default=True,
        description="Enable error tracking and reporting",
    )

    # ============================================================================
    # Development/Debug Settings
    # ============================================================================

    debug_mode: bool = Field(
        default=False,
        description="Enable debug mode with verbose logging",
    )

    profile_requests: bool = Field(
        default=False,
        description="Enable request profiling (performance impact)",
    )

    export_traces_to_console: bool = Field(
        default=False,
        description="Export traces to console (development only)",
    )


# Singleton instance
_settings: Optional[ObservabilitySettings] = None


def get_observability_settings() -> ObservabilitySettings:
    """
    Get observability settings instance.

    Returns:
        ObservabilitySettings instance
    """
    global _settings
    if _settings is None:
        _settings = ObservabilitySettings()
    return _settings


# Convenience export
observability_settings = get_observability_settings()

# Made with Bob