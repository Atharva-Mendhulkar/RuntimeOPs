"""
IBM Bob - OpenTelemetry Tracing
Distributed tracing with OpenTelemetry for request tracking and performance monitoring
"""

from contextlib import contextmanager
from typing import Any, Dict, Optional

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

from bob.config import settings


class TracingManager:
    """
    Manages OpenTelemetry tracing configuration and instrumentation.
    Provides utilities for creating spans and adding trace context.
    """

    _instance: Optional["TracingManager"] = None
    _tracer_provider: Optional[TracerProvider] = None
    _tracer: Optional[trace.Tracer] = None

    def __init__(self, service_name: str = "bob-repository-intelligence"):
        """
        Initialize OpenTelemetry tracing.

        Args:
            service_name: Name of the service for tracing
        """
        if not settings.enable_tracing:
            return

        # Create resource with service information
        resource = Resource.create(
            {
                "service.name": service_name,
                "service.version": "1.0.0",
                "deployment.environment": settings.environment,
            }
        )

        # Create tracer provider
        self._tracer_provider = TracerProvider(resource=resource)

        # Configure span exporter based on environment
        if settings.environment == "development":
            # Use console exporter for development
            console_exporter = ConsoleSpanExporter()
            self._tracer_provider.add_span_processor(
                BatchSpanProcessor(console_exporter)
            )

        # Add OTLP exporter for production/staging
        if settings.otel_exporter_otlp_endpoint:
            otlp_exporter = OTLPSpanExporter(
                endpoint=settings.otel_exporter_otlp_endpoint,
                insecure=settings.environment == "development",
            )
            self._tracer_provider.add_span_processor(
                BatchSpanProcessor(
                    otlp_exporter,
                    max_queue_size=2048,
                    max_export_batch_size=512,
                    schedule_delay_millis=5000,
                )
            )

        # Set global tracer provider
        trace.set_tracer_provider(self._tracer_provider)

        # Get tracer instance
        self._tracer = trace.get_tracer(__name__)

        # Auto-instrument libraries
        self._instrument_libraries()

    def _instrument_libraries(self):
        """Auto-instrument common libraries"""
        try:
            # Instrument HTTP clients
            HTTPXClientInstrumentor().instrument()
        except Exception as e:
            print(f"⚠️  Failed to instrument HTTPX: {e}")

        try:
            # Instrument Redis
            RedisInstrumentor().instrument()
        except Exception as e:
            print(f"⚠️  Failed to instrument Redis: {e}")

        try:
            # Instrument PostgreSQL
            Psycopg2Instrumentor().instrument()
        except Exception as e:
            print(f"⚠️  Failed to instrument Psycopg2: {e}")

    def instrument_fastapi(self, app):
        """
        Instrument FastAPI application.

        Args:
            app: FastAPI application instance
        """
        if not settings.enable_tracing:
            return

        try:
            FastAPIInstrumentor.instrument_app(app)
            print("✅ FastAPI instrumented for tracing")
        except Exception as e:
            print(f"⚠️  Failed to instrument FastAPI: {e}")

    def get_tracer(self) -> trace.Tracer:
        """
        Get tracer instance.

        Returns:
            OpenTelemetry tracer
        """
        if not settings.enable_tracing or not self._tracer:
            return trace.get_tracer(__name__)
        return self._tracer

    @contextmanager
    def create_span(
        self,
        name: str,
        attributes: Optional[Dict[str, Any]] = None,
        kind: trace.SpanKind = trace.SpanKind.INTERNAL,
    ):
        """
        Create a new span with attributes.

        Args:
            name: Span name
            attributes: Optional span attributes
            kind: Span kind (INTERNAL, SERVER, CLIENT, etc.)

        Yields:
            Span context manager
        """
        if not settings.enable_tracing:
            yield None
            return

        tracer = self.get_tracer()
        with tracer.start_as_current_span(name, kind=kind) as span:
            if attributes:
                for key, value in attributes.items():
                    # Convert value to string if it's not a primitive type
                    if isinstance(value, (str, int, float, bool)):
                        span.set_attribute(key, value)
                    else:
                        span.set_attribute(key, str(value))
            yield span

    def add_span_event(
        self,
        span: Optional[trace.Span],
        name: str,
        attributes: Optional[Dict[str, Any]] = None,
    ):
        """
        Add event to current span.

        Args:
            span: Span to add event to
            name: Event name
            attributes: Optional event attributes
        """
        if not settings.enable_tracing or not span:
            return

        if attributes:
            span.add_event(name, attributes)
        else:
            span.add_event(name)

    def set_span_error(self, span: Optional[trace.Span], error: Exception):
        """
        Mark span as error and record exception.

        Args:
            span: Span to mark as error
            error: Exception that occurred
        """
        if not settings.enable_tracing or not span:
            return

        span.set_status(trace.Status(trace.StatusCode.ERROR, str(error)))
        span.record_exception(error)

    def get_current_span(self) -> Optional[trace.Span]:
        """
        Get current active span.

        Returns:
            Current span or None
        """
        if not settings.enable_tracing:
            return None
        return trace.get_current_span()

    def get_trace_id(self) -> Optional[str]:
        """
        Get current trace ID.

        Returns:
            Trace ID as hex string or None
        """
        if not settings.enable_tracing:
            return None

        span = self.get_current_span()
        if span and span.get_span_context().is_valid:
            return format(span.get_span_context().trace_id, "032x")
        return None

    def get_span_id(self) -> Optional[str]:
        """
        Get current span ID.

        Returns:
            Span ID as hex string or None
        """
        if not settings.enable_tracing:
            return None

        span = self.get_current_span()
        if span and span.get_span_context().is_valid:
            return format(span.get_span_context().span_id, "016x")
        return None

    def shutdown(self):
        """Shutdown tracer provider and flush spans"""
        if self._tracer_provider:
            self._tracer_provider.shutdown()

    @classmethod
    def get_instance(cls) -> "TracingManager":
        """
        Get singleton instance of TracingManager.

        Returns:
            TracingManager instance
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance


# Convenience functions
def get_tracer() -> trace.Tracer:
    """Get tracer instance"""
    return TracingManager.get_instance().get_tracer()


def create_span(
    name: str,
    attributes: Optional[Dict[str, Any]] = None,
    kind: trace.SpanKind = trace.SpanKind.INTERNAL,
):
    """Create a new span"""
    return TracingManager.get_instance().create_span(name, attributes, kind)


def add_span_event(
    span: Optional[trace.Span],
    name: str,
    attributes: Optional[Dict[str, Any]] = None,
):
    """Add event to span"""
    TracingManager.get_instance().add_span_event(span, name, attributes)


def set_span_error(span: Optional[trace.Span], error: Exception):
    """Mark span as error"""
    TracingManager.get_instance().set_span_error(span, error)


def get_trace_id() -> Optional[str]:
    """Get current trace ID"""
    return TracingManager.get_instance().get_trace_id()


def get_span_id() -> Optional[str]:
    """Get current span ID"""
    return TracingManager.get_instance().get_span_id()


# Made with Bob