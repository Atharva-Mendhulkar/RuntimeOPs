"""
IBM Bob - Audit Logging
Comprehensive audit trail for security and compliance
"""

import json
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from bob.config import get_settings

settings = get_settings()


class AuditEventType(str, Enum):
    """Types of audit events"""

    # Authentication events
    LOGIN_SUCCESS = "auth.login.success"
    LOGIN_FAILURE = "auth.login.failure"
    TOKEN_REFRESH = "auth.token.refresh"
    TOKEN_REVOKED = "auth.token.revoked"
    API_KEY_CREATED = "auth.apikey.created"
    API_KEY_REVOKED = "auth.apikey.revoked"
    API_KEY_ROTATED = "auth.apikey.rotated"

    # Authorization events
    ACCESS_DENIED = "authz.access.denied"
    PERMISSION_GRANTED = "authz.permission.granted"
    PERMISSION_DENIED = "authz.permission.denied"

    # Data access events
    REPOSITORY_ACCESSED = "data.repo.accessed"
    FILE_ACCESSED = "data.file.accessed"
    SEARCH_EXECUTED = "data.search.executed"
    DEPENDENCY_GRAPH_QUERIED = "data.deps.queried"
    BLAST_RADIUS_COMPUTED = "data.blast.computed"

    # Administrative events
    USER_CREATED = "admin.user.created"
    USER_DELETED = "admin.user.deleted"
    USER_UPDATED = "admin.user.updated"
    ROLE_CHANGED = "admin.role.changed"
    REPOSITORY_ADDED = "admin.repo.added"
    REPOSITORY_REMOVED = "admin.repo.removed"

    # System events
    REINDEX_TRIGGERED = "system.reindex.triggered"
    REINDEX_COMPLETED = "system.reindex.completed"
    REINDEX_FAILED = "system.reindex.failed"
    CONFIGURATION_CHANGED = "system.config.changed"
    RATE_LIMIT_EXCEEDED = "system.ratelimit.exceeded"

    # Security events
    SUSPICIOUS_ACTIVITY = "security.suspicious"
    BRUTE_FORCE_DETECTED = "security.bruteforce"
    INJECTION_ATTEMPT = "security.injection"


class AuditLogger:
    """Logs audit events to PostgreSQL"""

    def __init__(self, db_connection):
        """
        Initialize audit logger.

        Args:
            db_connection: Database connection for storing audit logs
        """
        self.db = db_connection

    def log_event(
        self,
        event_type: AuditEventType,
        user_id: str,
        resource: str,
        action: str,
        result: str,
        metadata: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> str:
        """
        Log an audit event.

        Args:
            event_type: Type of audit event
            user_id: User identifier
            resource: Resource being accessed (e.g., repo_id, file_path)
            action: Action being performed
            result: Result of action ("success" or "failure")
            metadata: Additional event metadata
            ip_address: Client IP address
            user_agent: Client user agent
            request_id: Request correlation ID

        Returns:
            Audit log entry ID
        """
        cursor = self.db.cursor()

        # Serialize metadata
        metadata_json = json.dumps(metadata) if metadata else None

        # Insert audit log entry
        cursor.execute(
            """
            INSERT INTO audit_logs
            (event_type, user_id, resource, action, result, metadata,
             ip_address, user_agent, request_id, timestamp)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING log_id
            """,
            (
                event_type.value,
                user_id,
                resource,
                action,
                result,
                metadata_json,
                ip_address,
                user_agent,
                request_id,
                datetime.utcnow(),
            ),
        )

        log_id = cursor.fetchone()[0]
        self.db.commit()

        return log_id

    def log_authentication(
        self,
        user_id: str,
        success: bool,
        method: str = "jwt",
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        failure_reason: Optional[str] = None,
    ) -> str:
        """
        Log authentication attempt.

        Args:
            user_id: User identifier
            success: Whether authentication succeeded
            method: Authentication method (jwt, api_key)
            ip_address: Client IP address
            user_agent: Client user agent
            failure_reason: Reason for failure (if applicable)

        Returns:
            Audit log entry ID
        """
        event_type = AuditEventType.LOGIN_SUCCESS if success else AuditEventType.LOGIN_FAILURE

        metadata = {
            "method": method,
        }

        if failure_reason:
            metadata["failure_reason"] = failure_reason

        return self.log_event(
            event_type=event_type,
            user_id=user_id,
            resource="authentication",
            action="login",
            result="success" if success else "failure",
            metadata=metadata,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    def log_authorization(
        self,
        user_id: str,
        resource: str,
        action: str,
        granted: bool,
        required_scope: Optional[str] = None,
        user_scopes: Optional[List[str]] = None,
    ) -> str:
        """
        Log authorization check.

        Args:
            user_id: User identifier
            resource: Resource being accessed
            action: Action being performed
            granted: Whether access was granted
            required_scope: Required permission scope
            user_scopes: User's permission scopes

        Returns:
            Audit log entry ID
        """
        event_type = (
            AuditEventType.PERMISSION_GRANTED if granted else AuditEventType.PERMISSION_DENIED
        )

        metadata = {
            "required_scope": required_scope,
            "user_scopes": user_scopes,
        }

        return self.log_event(
            event_type=event_type,
            user_id=user_id,
            resource=resource,
            action=action,
            result="success" if granted else "failure",
            metadata=metadata,
        )

    def log_data_access(
        self,
        user_id: str,
        repo_id: str,
        resource_type: str,
        resource_path: str,
        query: Optional[str] = None,
        result_count: Optional[int] = None,
        request_id: Optional[str] = None,
    ) -> str:
        """
        Log data access event.

        Args:
            user_id: User identifier
            repo_id: Repository UUID
            resource_type: Type of resource (file, search, deps, etc.)
            resource_path: Path to resource
            query: Search query (if applicable)
            result_count: Number of results returned
            request_id: Request correlation ID

        Returns:
            Audit log entry ID
        """
        event_type_map = {
            "file": AuditEventType.FILE_ACCESSED,
            "search": AuditEventType.SEARCH_EXECUTED,
            "deps": AuditEventType.DEPENDENCY_GRAPH_QUERIED,
            "blast": AuditEventType.BLAST_RADIUS_COMPUTED,
        }

        event_type = event_type_map.get(resource_type, AuditEventType.REPOSITORY_ACCESSED)

        metadata: Dict[str, Any] = {
            "repo_id": repo_id,
            "resource_path": resource_path,
        }

        if query:
            metadata["query"] = query

        if result_count is not None:
            metadata["result_count"] = result_count

        return self.log_event(
            event_type=event_type,
            user_id=user_id,
            resource=f"{repo_id}:{resource_path}",
            action="read",
            result="success",
            metadata=metadata,
            request_id=request_id,
        )

    def log_admin_action(
        self,
        admin_user_id: str,
        action: str,
        target_user_id: Optional[str] = None,
        target_resource: Optional[str] = None,
        changes: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Log administrative action.

        Args:
            admin_user_id: Administrator user ID
            action: Action performed
            target_user_id: Target user ID (if applicable)
            target_resource: Target resource (if applicable)
            changes: Changes made

        Returns:
            Audit log entry ID
        """
        event_type_map = {
            "user_created": AuditEventType.USER_CREATED,
            "user_deleted": AuditEventType.USER_DELETED,
            "user_updated": AuditEventType.USER_UPDATED,
            "role_changed": AuditEventType.ROLE_CHANGED,
            "repo_added": AuditEventType.REPOSITORY_ADDED,
            "repo_removed": AuditEventType.REPOSITORY_REMOVED,
        }

        event_type = event_type_map.get(action, AuditEventType.USER_UPDATED)

        resource = target_user_id or target_resource or "system"

        metadata = {
            "action": action,
            "changes": changes,
        }

        return self.log_event(
            event_type=event_type,
            user_id=admin_user_id,
            resource=resource,
            action=action,
            result="success",
            metadata=metadata,
        )

    def log_security_event(
        self,
        event_type: AuditEventType,
        user_id: str,
        description: str,
        severity: str = "medium",
        ip_address: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Log security event.

        Args:
            event_type: Type of security event
            user_id: User identifier
            description: Event description
            severity: Event severity (low, medium, high, critical)
            ip_address: Client IP address
            metadata: Additional event metadata

        Returns:
            Audit log entry ID
        """
        if metadata is None:
            metadata = {}

        metadata["description"] = description
        metadata["severity"] = severity

        return self.log_event(
            event_type=event_type,
            user_id=user_id,
            resource="security",
            action="alert",
            result="detected",
            metadata=metadata,
            ip_address=ip_address,
        )

    def query_audit_log(
        self,
        user_id: Optional[str] = None,
        event_type: Optional[AuditEventType] = None,
        resource: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        result: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Query audit log with filters.

        Args:
            user_id: Filter by user ID
            event_type: Filter by event type
            resource: Filter by resource
            start_time: Filter by start time
            end_time: Filter by end time
            result: Filter by result (success/failure)
            limit: Maximum number of results
            offset: Result offset for pagination

        Returns:
            List of audit log entries
        """
        cursor = self.db.cursor()

        # Build query
        query = "SELECT * FROM audit_logs WHERE 1=1"
        params = []

        if user_id:
            query += " AND user_id = %s"
            params.append(user_id)

        if event_type:
            query += " AND event_type = %s"
            params.append(event_type.value)

        if resource:
            query += " AND resource = %s"
            params.append(resource)

        if start_time:
            query += " AND timestamp >= %s"
            params.append(start_time)

        if end_time:
            query += " AND timestamp <= %s"
            params.append(end_time)

        if result:
            query += " AND result = %s"
            params.append(result)

        query += " ORDER BY timestamp DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        cursor.execute(query, params)

        # Format results
        columns = [desc[0] for desc in cursor.description]
        results = []

        for row in cursor.fetchall():
            entry = dict(zip(columns, row))

            # Parse metadata JSON
            if entry.get("metadata"):
                entry["metadata"] = json.loads(entry["metadata"])

            results.append(entry)

        return results

    def get_user_activity_summary(
        self,
        user_id: str,
        days: int = 30,
    ) -> Dict[str, Any]:
        """
        Get activity summary for a user.

        Args:
            user_id: User identifier
            days: Number of days to look back

        Returns:
            Activity summary dictionary
        """
        cursor = self.db.cursor()

        start_time = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        start_time = start_time.replace(day=start_time.day - days)

        # Get event counts by type
        cursor.execute(
            """
            SELECT event_type, COUNT(*) as count
            FROM audit_logs
            WHERE user_id = %s AND timestamp >= %s
            GROUP BY event_type
            ORDER BY count DESC
            """,
            (user_id, start_time),
        )

        event_counts = {row[0]: row[1] for row in cursor.fetchall()}

        # Get total events
        total_events = sum(event_counts.values())

        # Get failed authentication attempts
        cursor.execute(
            """
            SELECT COUNT(*) FROM audit_logs
            WHERE user_id = %s
            AND event_type = %s
            AND timestamp >= %s
            """,
            (user_id, AuditEventType.LOGIN_FAILURE.value, start_time),
        )

        failed_logins = cursor.fetchone()[0]

        # Get most accessed repositories
        cursor.execute(
            """
            SELECT resource, COUNT(*) as count
            FROM audit_logs
            WHERE user_id = %s
            AND event_type IN (%s, %s, %s)
            AND timestamp >= %s
            GROUP BY resource
            ORDER BY count DESC
            LIMIT 10
            """,
            (
                user_id,
                AuditEventType.REPOSITORY_ACCESSED.value,
                AuditEventType.FILE_ACCESSED.value,
                AuditEventType.SEARCH_EXECUTED.value,
                start_time,
            ),
        )

        top_resources = [{"resource": row[0], "count": row[1]} for row in cursor.fetchall()]

        return {
            "user_id": user_id,
            "period_days": days,
            "total_events": total_events,
            "failed_logins": failed_logins,
            "event_counts": event_counts,
            "top_resources": top_resources,
        }

    def cleanup_old_logs(self, retention_days: int = 90) -> int:
        """
        Clean up audit logs older than retention period.

        Args:
            retention_days: Number of days to retain logs

        Returns:
            Number of logs deleted
        """
        cursor = self.db.cursor()

        cutoff_date = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        cutoff_date = cutoff_date.replace(day=cutoff_date.day - retention_days)

        cursor.execute(
            """
            DELETE FROM audit_logs
            WHERE timestamp < %s
            """,
            (cutoff_date,),
        )

        deleted_count = cursor.rowcount
        self.db.commit()

        return deleted_count


# Made with Bob
