"""
IBM Bob - Role-Based Access Control (RBAC)
Permission scopes, roles, and authorization checks
"""

from enum import Enum
from typing import Any, Dict, List, Optional

from bob.exceptions import AuthorizationError


class Scope(str, Enum):
    """Permission scopes for Bob operations"""

    # Read permissions
    READ_REPOSITORY = "repo:read"
    READ_CODE = "code:read"
    READ_DEPENDENCIES = "deps:read"

    # Write permissions
    WRITE_REPOSITORY = "repo:write"
    TRIGGER_REINDEX = "index:trigger"

    # Admin permissions
    ADMIN_USERS = "admin:users"
    ADMIN_KEYS = "admin:keys"
    ADMIN_SYSTEM = "admin:system"


class Role(str, Enum):
    """User roles with predefined permission sets"""

    VIEWER = "viewer"  # Read-only access
    DEVELOPER = "developer"  # Read + trigger reindex
    ADMIN = "admin"  # Full access
    SERVICE_ACCOUNT = "service"  # API-only access


# Role to permissions mapping
ROLE_PERMISSIONS: Dict[Role, List[Scope]] = {
    Role.VIEWER: [
        Scope.READ_REPOSITORY,
        Scope.READ_CODE,
        Scope.READ_DEPENDENCIES,
    ],
    Role.DEVELOPER: [
        Scope.READ_REPOSITORY,
        Scope.READ_CODE,
        Scope.READ_DEPENDENCIES,
        Scope.TRIGGER_REINDEX,
    ],
    Role.ADMIN: [
        # All scopes
        Scope.READ_REPOSITORY,
        Scope.READ_CODE,
        Scope.READ_DEPENDENCIES,
        Scope.WRITE_REPOSITORY,
        Scope.TRIGGER_REINDEX,
        Scope.ADMIN_USERS,
        Scope.ADMIN_KEYS,
        Scope.ADMIN_SYSTEM,
    ],
    Role.SERVICE_ACCOUNT: [
        # Configurable per service, default to read-only
        Scope.READ_REPOSITORY,
        Scope.READ_CODE,
        Scope.READ_DEPENDENCIES,
    ],
}


# Endpoint to required scope mapping
ENDPOINT_SCOPES: Dict[str, Optional[Scope]] = {
    "/api/v1/bob/search": Scope.READ_CODE,
    "/api/v1/bob/resolve-stack-trace": Scope.READ_CODE,
    "/api/v1/bob/dependency-graph": Scope.READ_DEPENDENCIES,
    "/api/v1/bob/blast-radius": Scope.READ_DEPENDENCIES,
    "/api/v1/bob/file": Scope.READ_CODE,
    "/api/v1/bob/commit-diff": Scope.READ_CODE,
    "/api/v1/bob/batch": Scope.READ_CODE,
    "/api/v1/bob/health": None,  # Public endpoint
}


class AuthorizationChecker:
    """Handles authorization checks for users and resources"""

    def __init__(self, db_connection):
        """
        Initialize authorization checker.

        Args:
            db_connection: Database connection for ACL lookups
        """
        self.db = db_connection

    def check_permission(self, user_scopes: List[str], required_scope: str) -> bool:
        """
        Check if user has required permission.

        Args:
            user_scopes: List of user's permission scopes
            required_scope: Required scope for operation

        Returns:
            True if user has permission
        """
        # Admin scope grants all permissions
        if Scope.ADMIN_SYSTEM.value in user_scopes:
            return True

        # Check if required scope is in user's scopes
        return required_scope in user_scopes

    def check_endpoint_permission(
        self,
        user_scopes: List[str],
        endpoint: str,
    ) -> bool:
        """
        Check if user can access endpoint.

        Args:
            user_scopes: List of user's permission scopes
            endpoint: API endpoint path

        Returns:
            True if user has permission

        Raises:
            AuthorizationError: If permission denied
        """
        required_scope = ENDPOINT_SCOPES.get(endpoint)

        # Public endpoint
        if required_scope is None:
            return True

        # Check permission
        if not self.check_permission(user_scopes, required_scope.value):
            raise AuthorizationError(
                f"Insufficient permissions for {endpoint}. Required: {required_scope.value}"
            )

        return True

    def check_repository_access(
        self,
        user_id: str,
        repo_id: str,
        action: str = "read",
    ) -> bool:
        """
        Check if user can access specific repository.

        Args:
            user_id: User identifier
            repo_id: Repository UUID
            action: Action type ('read' or 'write')

        Returns:
            True if user has access

        Raises:
            AuthorizationError: If access denied
        """
        # Check if repository is public
        if self._is_public_repository(repo_id):
            return True

        # Check organization membership
        if self._is_org_member(user_id, repo_id):
            return True

        # Check explicit ACL
        if self._has_acl_access(user_id, repo_id, action):
            return True

        raise AuthorizationError(
            f"User {user_id} does not have {action} access to repository {repo_id}"
        )

    def get_accessible_repositories(self, user_id: str) -> List[str]:
        """
        Get list of repositories user can access.

        Args:
            user_id: User identifier

        Returns:
            List of repository IDs
        """
        cursor = self.db.cursor()

        # Get public repositories
        cursor.execute("""
            SELECT repo_id FROM repositories
            WHERE is_public = TRUE
            """)
        public_repos = [row[0] for row in cursor.fetchall()]

        # Get repositories from organization membership
        cursor.execute(
            """
            SELECT DISTINCT r.repo_id
            FROM repositories r
            JOIN organizations o ON r.organization_id = o.org_id
            JOIN organization_members om ON o.org_id = om.org_id
            WHERE om.user_id = %s
            """,
            (user_id,),
        )
        org_repos = [row[0] for row in cursor.fetchall()]

        # Get repositories from explicit ACL
        cursor.execute(
            """
            SELECT repo_id FROM repository_acl
            WHERE user_id = %s AND (action = 'read' OR action = 'write')
            """,
            (user_id,),
        )
        acl_repos = [row[0] for row in cursor.fetchall()]

        # Combine and deduplicate
        all_repos = list(set(public_repos + org_repos + acl_repos))
        return all_repos

    def grant_repository_access(
        self,
        user_id: str,
        repo_id: str,
        action: str = "read",
    ) -> bool:
        """
        Grant user access to repository.

        Args:
            user_id: User identifier
            repo_id: Repository UUID
            action: Action type ('read' or 'write')

        Returns:
            True if access granted
        """
        cursor = self.db.cursor()
        cursor.execute(
            """
            INSERT INTO repository_acl (user_id, repo_id, action, granted_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (user_id, repo_id, action) DO NOTHING
            """,
            (user_id, repo_id, action),
        )
        self.db.commit()
        return True

    def revoke_repository_access(
        self,
        user_id: str,
        repo_id: str,
        action: Optional[str] = None,
    ) -> bool:
        """
        Revoke user access to repository.

        Args:
            user_id: User identifier
            repo_id: Repository UUID
            action: Action type to revoke (None = all actions)

        Returns:
            True if access revoked
        """
        cursor = self.db.cursor()

        if action:
            cursor.execute(
                """
                DELETE FROM repository_acl
                WHERE user_id = %s AND repo_id = %s AND action = %s
                """,
                (user_id, repo_id, action),
            )
        else:
            cursor.execute(
                """
                DELETE FROM repository_acl
                WHERE user_id = %s AND repo_id = %s
                """,
                (user_id, repo_id),
            )

        self.db.commit()
        return cursor.rowcount > 0

    def get_user_role(self, user_id: str) -> Role:
        """
        Get user's role.

        Args:
            user_id: User identifier

        Returns:
            User's role
        """
        cursor = self.db.cursor()
        cursor.execute(
            """
            SELECT role FROM users
            WHERE user_id = %s
            """,
            (user_id,),
        )

        row = cursor.fetchone()
        if not row:
            return Role.VIEWER  # Default role

        return Role(row[0])

    def get_user_scopes(self, user_id: str) -> List[str]:
        """
        Get user's permission scopes based on role.

        Args:
            user_id: User identifier

        Returns:
            List of permission scopes
        """
        role = self.get_user_role(user_id)
        scopes = ROLE_PERMISSIONS.get(role, [])
        return [scope.value for scope in scopes]

    def assign_role(self, user_id: str, role: Role) -> bool:
        """
        Assign role to user.

        Args:
            user_id: User identifier
            role: Role to assign

        Returns:
            True if role assigned
        """
        cursor = self.db.cursor()
        cursor.execute(
            """
            UPDATE users
            SET role = %s, updated_at = NOW()
            WHERE user_id = %s
            """,
            (role.value, user_id),
        )
        self.db.commit()
        return cursor.rowcount > 0

    def _is_public_repository(self, repo_id: str) -> bool:
        """Check if repository is public"""
        cursor = self.db.cursor()
        cursor.execute(
            """
            SELECT is_public FROM repositories
            WHERE repo_id = %s
            """,
            (repo_id,),
        )

        row = cursor.fetchone()
        return row[0] if row else False

    def _is_org_member(self, user_id: str, repo_id: str) -> bool:
        """Check if user is member of repository's organization"""
        cursor = self.db.cursor()
        cursor.execute(
            """
            SELECT COUNT(*) FROM organization_members om
            JOIN repositories r ON om.org_id = r.organization_id
            WHERE om.user_id = %s AND r.repo_id = %s
            """,
            (user_id, repo_id),
        )

        row = cursor.fetchone()
        return row[0] > 0 if row else False

    def _has_acl_access(self, user_id: str, repo_id: str, action: str) -> bool:
        """Check if user has explicit ACL access"""
        cursor = self.db.cursor()
        cursor.execute(
            """
            SELECT COUNT(*) FROM repository_acl
            WHERE user_id = %s AND repo_id = %s AND action = %s
            """,
            (user_id, repo_id, action),
        )

        row = cursor.fetchone()
        return row[0] > 0 if row else False


def get_scopes_for_role(role: Role) -> List[str]:
    """
    Get permission scopes for a role.

    Args:
        role: User role

    Returns:
        List of permission scope strings
    """
    scopes = ROLE_PERMISSIONS.get(role, [])
    return [scope.value for scope in scopes]


def validate_scopes(scopes: List[str]) -> bool:
    """
    Validate that all scopes are valid.

    Args:
        scopes: List of scope strings

    Returns:
        True if all scopes are valid
    """
    valid_scopes = {scope.value for scope in Scope}
    return all(scope in valid_scopes for scope in scopes)


# Made with Bob
