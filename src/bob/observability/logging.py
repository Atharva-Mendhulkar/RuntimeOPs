"""
IBM Bob - Structured Logging
JSON-based structured logging with context propagation and trace correlation
"""

import logging
import sys
from typing import Any, Dict, Optional

import structlog
from structlog.processors import (
    JSONRenderer,
    TimeStamper,
    add_log_level,
    format_exc_info,
)
from structlog.stdlib import (
    BoundLogger,
    LoggerFactory,
    add_logger_name,
    filter_by_level,
)

from bob.config import settings


class LoggingManager:
    """
    Manages structured logging configuration.
    Provides JSON-formatted logs with trace correlation and context propagation.
    """

    _instance: Optional["LoggingManager"] = None
    _configured: bool = False

    def __init__(self):
        """Configure structured logging"""
        if self._configured:
            return

        # Configure standard library logging
        logging.basicConfig(
            format="%(message)s",
            stream=sys.stdout,
            level=getattr(logging, settings.log_level.upper()),
        )

        # Configure structlog
        structlog.configure(
            processors=[
                # Add contextvars (request_id, user_id, etc.)
                structlog.contextvars.merge_contextvars,
                # Add logger name
                add_logger_name,
                # Add log level
                add_log_level,
                # Add timestamp
                TimeStamper(fmt="iso", utc=True),
                # Add stack info for errors
                structlog.processors.StackInfoRenderer(),
                # Format exceptions
                format_exc_info,
                # Filter by log level
                filter_by_level,
                # Render as JSON
                (
                    JSONRenderer()
                    if settings.environment != "development"
                    else structlog.dev.ConsoleRenderer()
                ),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(
                getattr(logging, settings.log_level.upper())
            ),
            context_class=dict,
            logger_factory=LoggerFactory(),
            cache_logger_on_first_use=True,
        )

        self._configured = True

    def get_logger(self, name: str) -> BoundLogger:
        """
        Get structured logger instance.

        Args:
            name: Logger name (typically __name__)

        Returns:
            Structured logger instance
        """
        return structlog.get_logger(name)

    @staticmethod
    def bind_context(**kwargs: Any) -> None:
        """
        Bind context variables to all subsequent log messages.

        Args:
            **kwargs: Context variables to bind
        """
        structlog.contextvars.bind_contextvars(**kwargs)

    @staticmethod
    def unbind_context(*keys: str) -> None:
        """
        Unbind context variables.

        Args:
            *keys: Context variable keys to unbind
        """
        structlog.contextvars.unbind_contextvars(*keys)

    @staticmethod
    def clear_context() -> None:
        """Clear all context variables"""
        structlog.contextvars.clear_contextvars()

    @staticmethod
    def get_context() -> Dict[str, Any]:
        """
        Get current context variables.

        Returns:
            Dictionary of context variables
        """
        return structlog.contextvars.get_contextvars()

    @classmethod
    def get_instance(cls) -> "LoggingManager":
        """
        Get singleton instance of LoggingManager.

        Returns:
            LoggingManager instance
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance


# Convenience functions
def get_logger(name: str) -> BoundLogger:
    """
    Get structured logger instance.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Structured logger instance
    """
    return LoggingManager.get_instance().get_logger(name)


def bind_context(**kwargs: Any) -> None:
    """
    Bind context variables to all subsequent log messages.

    Args:
        **kwargs: Context variables to bind
    """
    LoggingManager.bind_context(**kwargs)


def unbind_context(*keys: str) -> None:
    """
    Unbind context variables.

    Args:
        *keys: Context variable keys to unbind
    """
    LoggingManager.unbind_context(*keys)


def clear_context() -> None:
    """Clear all context variables"""
    LoggingManager.clear_context()


def get_context() -> Dict[str, Any]:
    """
    Get current context variables.

    Returns:
        Dictionary of context variables
    """
    return LoggingManager.get_context()


# Initialize logging on module import
LoggingManager.get_instance()

# Made with Bob
