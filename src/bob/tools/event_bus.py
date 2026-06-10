"""
IBM Bob - Event Bus Integration
Event emission and subscription for RuntimeOps Event Bus
"""

import json
import logging
from datetime import datetime
from enum import Enum
from typing import Any, Callable

from pydantic import BaseModel, Field

from bob.config import get_settings
from bob.storage.cache import FileCache

logger = logging.getLogger(__name__)
settings = get_settings()


# ============================================================================
# Event Models
# ============================================================================


class EventType(str, Enum):
    """Bob event types"""

    # Indexing events
    INDEX_STARTED = "index_started"
    INDEX_COMPLETE = "index_complete"
    INDEX_FAILED = "index_failed"
    INDEX_PROGRESS = "index_progress"

    # Query events
    QUERY_EXECUTED = "query_executed"
    QUERY_FAILED = "query_failed"

    # Incident events
    INCIDENT_INTAKE = "incident_intake"
    INCIDENT_RESOLVED = "incident_resolved"

    # Repository events
    REPO_ADDED = "repo_added"
    REPO_UPDATED = "repo_updated"
    REPO_REMOVED = "repo_removed"

    # Webhook events
    GITHUB_PUSH = "github_push"
    GITHUB_PR = "github_pr"


class BobEvent(BaseModel):
    """
    Bob event model for event bus communication.

    All events emitted by Bob follow this schema.
    """

    event_type: EventType = Field(..., description="Event type")
    repo_id: str = Field(..., description="Repository UUID")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Event timestamp (UTC)",
    )
    data: dict[str, Any] = Field(
        default_factory=dict,
        description="Event-specific data",
    )
    source: str = Field(
        default="bob",
        description="Event source system",
    )
    correlation_id: str | None = Field(
        None,
        description="Correlation ID for tracing",
    )


# ============================================================================
# Event Emitter
# ============================================================================


class EventEmitter:
    """
    Emits events to RuntimeOps Event Bus.

    Supports both Redis Pub/Sub and Kafka (configurable).
    """

    def __init__(self, backend: str = "redis"):
        """
        Initialize event emitter.

        Args:
            backend: Event bus backend ('redis' or 'kafka')
        """
        self.backend = backend
        self._redis_client = None
        self._kafka_producer = None

        logger.info(f"EventEmitter initialized with backend: {backend}")

    def emit(self, event: BobEvent) -> None:
        """
        Emit event to event bus.

        Args:
            event: BobEvent to emit

        Example:
            >>> emitter = EventEmitter()
            >>> event = BobEvent(
            ...     event_type=EventType.INDEX_COMPLETE,
            ...     repo_id="550e8400-...",
            ...     data={"files_indexed": 1234, "duration_ms": 5000}
            ... )
            >>> emitter.emit(event)
        """
        try:
            if self.backend == "redis":
                self._emit_redis(event)
            elif self.backend == "kafka":
                self._emit_kafka(event)
            else:
                logger.error(f"Unknown event bus backend: {self.backend}")

        except Exception as e:
            logger.error(f"Failed to emit event: {e}", exc_info=True)

    def _emit_redis(self, event: BobEvent) -> None:
        """Emit event via Redis Pub/Sub"""
        with FileCache() as cache:
            channel = f"bob:events:{event.event_type.value}"
            message = event.model_dump_json()

            # Publish to Redis channel
            cache.redis_client.publish(channel, message)

            logger.debug(f"Emitted event to Redis: {event.event_type.value}")

    def _emit_kafka(self, event: BobEvent) -> None:
        """Emit event via Kafka"""
        # TODO: Implement Kafka producer
        logger.warning("Kafka event emission not yet implemented")

        # Placeholder for Kafka implementation:
        # topic = f"bob.events.{event.event_type.value}"
        # self._kafka_producer.send(topic, value=event.model_dump())

    def emit_index_started(
        self,
        repo_id: str,
        scope: str,
        correlation_id: str | None = None,
    ) -> None:
        """Emit index started event"""
        event = BobEvent(
            event_type=EventType.INDEX_STARTED,
            repo_id=repo_id,
            data={"scope": scope},
            correlation_id=correlation_id,
        )
        self.emit(event)

    def emit_index_complete(
        self,
        repo_id: str,
        files_indexed: int,
        duration_ms: float,
        correlation_id: str | None = None,
    ) -> None:
        """Emit index complete event"""
        event = BobEvent(
            event_type=EventType.INDEX_COMPLETE,
            repo_id=repo_id,
            data={
                "files_indexed": files_indexed,
                "duration_ms": duration_ms,
                "status": "success",
            },
            correlation_id=correlation_id,
        )
        self.emit(event)

    def emit_index_failed(
        self,
        repo_id: str,
        error: str,
        correlation_id: str | None = None,
    ) -> None:
        """Emit index failed event"""
        event = BobEvent(
            event_type=EventType.INDEX_FAILED,
            repo_id=repo_id,
            data={"error": error, "status": "failed"},
            correlation_id=correlation_id,
        )
        self.emit(event)

    def emit_query_executed(
        self,
        repo_id: str,
        query_type: str,
        duration_ms: float,
        result_count: int,
    ) -> None:
        """Emit query executed event"""
        event = BobEvent(
            event_type=EventType.QUERY_EXECUTED,
            repo_id=repo_id,
            data={
                "query_type": query_type,
                "duration_ms": duration_ms,
                "result_count": result_count,
            },
        )
        self.emit(event)


# ============================================================================
# Event Subscriber
# ============================================================================


class EventSubscriber:
    """
    Subscribes to events from RuntimeOps Event Bus.

    Handles incident intake events and webhook events.
    """

    def __init__(self, backend: str = "redis"):
        """
        Initialize event subscriber.

        Args:
            backend: Event bus backend ('redis' or 'kafka')
        """
        self.backend = backend
        self._redis_client = None
        self._kafka_consumer = None
        self._handlers: dict[EventType, list[Callable]] = {}

        logger.info(f"EventSubscriber initialized with backend: {backend}")

    def register_handler(
        self,
        event_type: EventType,
        handler: Callable[[BobEvent], None],
    ) -> None:
        """
        Register event handler.

        Args:
            event_type: Event type to handle
            handler: Handler function that takes BobEvent

        Example:
            >>> subscriber = EventSubscriber()
            >>> def handle_incident(event: BobEvent):
            ...     print(f"Incident: {event.data}")
            >>> subscriber.register_handler(EventType.INCIDENT_INTAKE, handle_incident)
        """
        if event_type not in self._handlers:
            self._handlers[event_type] = []

        self._handlers[event_type].append(handler)
        logger.info(f"Registered handler for {event_type.value}")

    def subscribe(self, event_types: list[EventType]) -> None:
        """
        Subscribe to event types.

        Args:
            event_types: List of event types to subscribe to

        Example:
            >>> subscriber = EventSubscriber()
            >>> subscriber.subscribe([EventType.INCIDENT_INTAKE, EventType.GITHUB_PUSH])
        """
        if self.backend == "redis":
            self._subscribe_redis(event_types)
        elif self.backend == "kafka":
            self._subscribe_kafka(event_types)
        else:
            logger.error(f"Unknown event bus backend: {self.backend}")

    def _subscribe_redis(self, event_types: list[EventType]) -> None:
        """Subscribe to events via Redis Pub/Sub"""
        with FileCache() as cache:
            pubsub = cache.redis_client.pubsub()

            # Subscribe to channels
            channels = [f"bob:events:{et.value}" for et in event_types]
            pubsub.subscribe(*channels)

            logger.info(f"Subscribed to Redis channels: {channels}")

            # Listen for messages
            for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        event_data = json.loads(message["data"])
                        event = BobEvent(**event_data)
                        self._handle_event(event)
                    except Exception as e:
                        logger.error(f"Failed to process event: {e}", exc_info=True)

    def _subscribe_kafka(self, event_types: list[EventType]) -> None:
        """Subscribe to events via Kafka"""
        # TODO: Implement Kafka consumer
        logger.warning("Kafka event subscription not yet implemented")

    def _handle_event(self, event: BobEvent) -> None:
        """Handle received event"""
        handlers = self._handlers.get(event.event_type, [])

        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error(
                    f"Handler failed for {event.event_type.value}: {e}",
                    exc_info=True,
                )


# ============================================================================
# Incident Event Handlers
# ============================================================================


class IncidentEventHandler:
    """
    Handles incident-related events.

    Triggers context snapshots on incident events.
    """

    def __init__(self):
        self.emitter = EventEmitter()
        logger.info("IncidentEventHandler initialized")

    def handle_incident_intake(self, event: BobEvent) -> None:
        """
        Handle incident intake event.

        Creates context snapshot for the incident.

        Args:
            event: Incident intake event
        """
        try:
            incident_id = event.data.get("incident_id")
            repo_id = event.repo_id

            logger.info(f"Handling incident intake: {incident_id}")

            # Create context snapshot
            from bob.tools.langgraph_integration import BobStateManager

            state_manager = BobStateManager()
            snapshot_id = state_manager.create_snapshot(incident_id, repo_id)

            logger.info(f"Created context snapshot: {snapshot_id}")

            # Emit snapshot created event
            self.emitter.emit(
                BobEvent(
                    event_type=EventType.INDEX_PROGRESS,
                    repo_id=repo_id,
                    data={
                        "incident_id": incident_id,
                        "snapshot_id": snapshot_id,
                        "status": "snapshot_created",
                    },
                    correlation_id=event.correlation_id,
                )
            )

        except Exception as e:
            logger.error(f"Failed to handle incident intake: {e}", exc_info=True)

    def handle_incident_resolved(self, event: BobEvent) -> None:
        """
        Handle incident resolved event.

        Clears context snapshot.

        Args:
            event: Incident resolved event
        """
        try:
            incident_id = event.data.get("incident_id")
            repo_id = event.repo_id

            logger.info(f"Handling incident resolved: {incident_id}")

            # Clear context snapshot
            from bob.tools.langgraph_integration import BobStateManager

            state_manager = BobStateManager()
            snapshot_id = f"{incident_id}:{repo_id}"
            state_manager.clear_snapshot(snapshot_id)

            logger.info(f"Cleared context snapshot: {snapshot_id}")

        except Exception as e:
            logger.error(f"Failed to handle incident resolved: {e}", exc_info=True)


# ============================================================================
# Webhook Event Handlers
# ============================================================================


class WebhookEventHandler:
    """
    Handles webhook events from GitHub.

    Triggers incremental reindexing on push events.
    """

    def __init__(self):
        self.emitter = EventEmitter()
        logger.info("WebhookEventHandler initialized")

    def handle_github_push(self, event: BobEvent) -> None:
        """
        Handle GitHub push event.

        Triggers incremental reindex for the repository.

        Args:
            event: GitHub push event
        """
        try:
            repo_id = event.repo_id
            commits = event.data.get("commits", [])

            logger.info(f"Handling GitHub push: {len(commits)} commits to {repo_id}")

            # Trigger incremental reindex
            from bob.tools.bob_tools import trigger_reindex

            job_id = trigger_reindex(repo_id, scope="incremental")

            logger.info(f"Triggered incremental reindex: job_id={job_id}")

            # Emit index started event
            self.emitter.emit_index_started(
                repo_id=repo_id,
                scope="incremental",
                correlation_id=event.correlation_id,
            )

        except Exception as e:
            logger.error(f"Failed to handle GitHub push: {e}", exc_info=True)

    def handle_github_pr(self, event: BobEvent) -> None:
        """
        Handle GitHub pull request event.

        Could trigger analysis of PR changes.

        Args:
            event: GitHub PR event
        """
        try:
            repo_id = event.repo_id
            pr_number = event.data.get("pr_number")
            action = event.data.get("action")

            logger.info(f"Handling GitHub PR: #{pr_number} ({action}) in {repo_id}")

            # TODO: Implement PR analysis
            # - Get changed files from PR
            # - Compute blast radius
            # - Get risk context
            # - Post analysis as PR comment

        except Exception as e:
            logger.error(f"Failed to handle GitHub PR: {e}", exc_info=True)


# ============================================================================
# Event Bus Manager
# ============================================================================


class EventBusManager:
    """
    Manages event emission and subscription for Bob.

    Provides high-level interface for event bus operations.
    """

    def __init__(self, backend: str = "redis"):
        """
        Initialize event bus manager.

        Args:
            backend: Event bus backend ('redis' or 'kafka')
        """
        self.emitter = EventEmitter(backend)
        self.subscriber = EventSubscriber(backend)

        # Register default handlers
        self._register_default_handlers()

        logger.info("EventBusManager initialized")

    def _register_default_handlers(self) -> None:
        """Register default event handlers"""
        incident_handler = IncidentEventHandler()
        webhook_handler = WebhookEventHandler()

        # Incident handlers
        self.subscriber.register_handler(
            EventType.INCIDENT_INTAKE,
            incident_handler.handle_incident_intake,
        )
        self.subscriber.register_handler(
            EventType.INCIDENT_RESOLVED,
            incident_handler.handle_incident_resolved,
        )

        # Webhook handlers
        self.subscriber.register_handler(
            EventType.GITHUB_PUSH,
            webhook_handler.handle_github_push,
        )
        self.subscriber.register_handler(
            EventType.GITHUB_PR,
            webhook_handler.handle_github_pr,
        )

        logger.info("Registered default event handlers")

    def start_listening(self) -> None:
        """
        Start listening for events.

        Subscribes to all relevant event types.
        """
        event_types = [
            EventType.INCIDENT_INTAKE,
            EventType.INCIDENT_RESOLVED,
            EventType.GITHUB_PUSH,
            EventType.GITHUB_PR,
        ]

        logger.info("Starting event bus listener...")
        self.subscriber.subscribe(event_types)


# Made with Bob
