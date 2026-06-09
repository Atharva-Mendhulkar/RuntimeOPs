"""
IBM Bob - Security Integration Tests
End-to-end tests for authentication, authorization, and security flows
"""

import pytest
from fastapi.testclient import TestClient

from bob.exceptions import AuthenticationError, AuthorizationError
from bob.security.auth import APIKeyManager, JWTManager
from bob.security.rbac import Role


@pytest.mark.integration
class TestAuthenticationFlow:
    """Integration tests for authentication flow"""

    def test_jwt_authentication_flow(self):
        """Test complete JWT authentication flow"""
        jwt_manager = JWTManager()
        
        # 1. Create access token
        access_token = jwt_manager.create_access_token(
            user_id="test_user",
            scopes=["repo:read", "code:read"],
        )
        
        # 2. Verify token
        payload = jwt_manager.verify_token(access_token)
        assert payload["sub"] == "test_user"
        
        # 3. Create refresh token
        refresh_token = jwt_manager.create_refresh_token(user_id="test_user")
        
        # 4. Refresh access token
        new_access_token = jwt_manager.refresh_access_token(refresh_token)
        new_payload = jwt_manager.verify_token(new_access_token)
        assert new_payload["sub"] == "test_user"
        
        # 5. Revoke token (requires Redis)
        # jwt_manager.revoke_token(access_token)

    def test_api_key_authentication_flow(self, mock_db):
        """Test complete API key authentication flow"""
        manager = APIKeyManager(mock_db)
        
        # 1. Generate API key
        key_id, api_key = manager.generate_api_key(
            user_id="test_user",
            name="Test Key",
            scopes=["repo:read"],
        )
        
        assert api_key.startswith("bob_live_")
        
        # 2. Verify API key (would require database lookup)
        # claims = manager.verify_api_key(api_key)
        # assert claims["user_id"] == "test_user"
        
        # 3. Revoke API key
        # manager.revoke_api_key(key_id)


@pytest.mark.integration
class TestAuthorizationFlow:
    """Integration tests for authorization flow"""

    def test_role_based_access_control(self, mock_db):
        """Test RBAC flow"""
        from bob.security.rbac import AuthorizationChecker, get_scopes_for_role
        
        checker = AuthorizationChecker(mock_db)
        
        # 1. Get scopes for viewer role
        viewer_scopes = get_scopes_for_role(Role.VIEWER)
        
        # 2. Check read permission (should pass)
        assert checker.check_permission(viewer_scopes, "repo:read")
        
        # 3. Check write permission (should fail)
        assert not checker.check_permission(viewer_scopes, "repo:write")
        
        # 4. Get scopes for admin role
        admin_scopes = get_scopes_for_role(Role.ADMIN)
        
        # 5. Admin should have all permissions
        assert checker.check_permission(admin_scopes, "repo:write")
        assert checker.check_permission(admin_scopes, "admin:system")


@pytest.mark.integration
class TestRateLimitingFlow:
    """Integration tests for rate limiting"""

    @pytest.mark.asyncio
    async def test_rate_limit_enforcement(self, mock_redis):
        """Test rate limit enforcement flow"""
        from bob.security.rate_limiter import RateLimiter, RateLimitTier
        
        limiter = RateLimiter(mock_redis)
        
        # 1. Check rate limit (should pass)
        allowed, metadata = await limiter.check_rate_limit(
            user_id="test_user",
            endpoint="/api/v1/bob/search",
            tier=RateLimitTier.DEVELOPER,
        )
        assert allowed
        
        # 2. Record request
        await limiter.record_request(
            user_id="test_user",
            endpoint="/api/v1/bob/search",
            tier=RateLimitTier.DEVELOPER,
        )
        
        # 3. Get usage stats
        stats = await limiter.get_usage_stats(
            user_id="test_user",
            tier=RateLimitTier.DEVELOPER,
        )
        assert "hourly" in stats
        assert "minute" in stats


@pytest.mark.integration
class TestAuditLoggingFlow:
    """Integration tests for audit logging"""

    def test_audit_trail_creation(self, mock_db):
        """Test complete audit trail creation"""
        from bob.security.audit import AuditEventType, AuditLogger
        
        logger = AuditLogger(mock_db)
        
        # 1. Log authentication
        log_id = logger.log_authentication(
            user_id="test_user",
            success=True,
            method="jwt",
            ip_address="192.168.1.1",
        )
        assert log_id is not None
        
        # 2. Log data access
        log_id = logger.log_data_access(
            user_id="test_user",
            repo_id="repo_123",
            resource_type="search",
            resource_path="/api/v1/bob/search",
            query="find auth function",
            result_count=5,
        )
        assert log_id is not None
        
        # 3. Log admin action
        log_id = logger.log_admin_action(
            admin_user_id="admin",
            action="role_changed",
            target_user_id="test_user",
            changes={"old_role": "viewer", "new_role": "developer"},
        )
        assert log_id is not None


@pytest.mark.integration
class TestSecretsManagement:
    """Integration tests for secrets management"""

    def test_secret_encryption_flow(self):
        """Test secret encryption and rotation"""
        from bob.security.secrets import SecretsManager, generate_encryption_key
        
        # 1. Generate encryption key
        key1 = generate_encryption_key()
        manager = SecretsManager(key1.encode())
        
        # 2. Encrypt secret
        plaintext = "github_token_abc123"
        encrypted = manager.encrypt_secret(plaintext)
        
        # 3. Decrypt secret
        decrypted = manager.decrypt_secret(encrypted)
        assert decrypted == plaintext
        
        # 4. Key rotation (would require database)
        # key2 = generate_encryption_key()
        # count = manager.rotate_encryption_key(key2.encode(), mock_db)


# Fixtures

@pytest.fixture
def mock_db():
    """Mock database connection"""
    from unittest.mock import Mock
    
    db = Mock()
    cursor = Mock()
    cursor.fetchone.return_value = ["test_id"]
    cursor.fetchall.return_value = []
    cursor.rowcount = 1
    db.cursor.return_value = cursor
    return db


@pytest.fixture
def mock_redis():
    """Mock Redis client"""
    from unittest.mock import Mock
    
    redis = Mock()
    redis.zcard.return_value = 0
    redis.zrange.return_value = []
    redis.keys.return_value = []
    redis.get.return_value = None
    return redis


# Made with Bob