"""
IBM Bob - Security Unit Tests
Tests for authentication, authorization, rate limiting, and validation
"""

import time
from datetime import datetime, timedelta
from unittest.mock import MagicMock, Mock, patch

import pytest

from bob.exceptions import (
    AuthenticationError,
    AuthorizationError,
    EncryptionError,
    InvalidQueryError,
    InvalidTokenError,
    RateLimitExceededError,
)
from bob.security.audit import AuditEventType, AuditLogger
from bob.security.auth import APIKeyManager, JWTManager
from bob.security.rate_limiter import RateLimiter, RateLimitTier
from bob.security.rbac import AuthorizationChecker, Role, Scope, get_scopes_for_role
from bob.security.secrets import (
    SecretsManager,
    SecretString,
    generate_encryption_key,
    mask_secret,
    sanitize_for_logging,
    validate_encryption_key,
)
from bob.security.validation import QueryValidator, RequestValidator

# ============================================================================
# JWT Manager Tests
# ============================================================================


class TestJWTManager:
    """Tests for JWT token management"""

    def test_create_access_token(self):
        """Test JWT access token creation"""
        jwt_manager = JWTManager()

        token = jwt_manager.create_access_token(
            user_id="test_user",
            scopes=["repo:read", "code:read"],
        )

        assert isinstance(token, str)
        assert len(token) > 0

    def test_verify_valid_token(self):
        """Test verification of valid JWT token"""
        jwt_manager = JWTManager()

        token = jwt_manager.create_access_token(
            user_id="test_user",
            scopes=["repo:read"],
        )

        payload = jwt_manager.verify_token(token)

        assert payload["sub"] == "test_user"
        assert "repo:read" in payload["scopes"]
        assert "exp" in payload
        assert "iat" in payload
        assert "jti" in payload

    def test_verify_expired_token(self):
        """Test verification of expired token"""
        jwt_manager = JWTManager()

        # Create token that expires immediately
        token = jwt_manager.create_access_token(
            user_id="test_user",
            scopes=["repo:read"],
            expires_delta=timedelta(seconds=-1),
        )

        with pytest.raises(InvalidTokenError, match="expired"):
            jwt_manager.verify_token(token)

    def test_create_refresh_token(self):
        """Test refresh token creation"""
        jwt_manager = JWTManager()

        token = jwt_manager.create_refresh_token(user_id="test_user")

        assert isinstance(token, str)
        payload = jwt_manager.verify_token(token)
        assert payload["type"] == "refresh"

    def test_refresh_access_token(self):
        """Test refreshing access token"""
        jwt_manager = JWTManager()

        refresh_token = jwt_manager.create_refresh_token(user_id="test_user")
        new_access_token = jwt_manager.refresh_access_token(refresh_token)

        assert isinstance(new_access_token, str)
        payload = jwt_manager.verify_token(new_access_token)
        assert payload["type"] == "access"


# ============================================================================
# API Key Manager Tests
# ============================================================================


class TestAPIKeyManager:
    """Tests for API key management"""

    @pytest.fixture
    def mock_db(self):
        """Mock database connection"""
        db = Mock()
        cursor = Mock()
        db.cursor.return_value = cursor
        return db

    def test_generate_api_key(self, mock_db):
        """Test API key generation"""
        manager = APIKeyManager(mock_db)

        key_id, api_key = manager.generate_api_key(
            user_id="test_user",
            name="Test Key",
            scopes=["repo:read"],
            environment="live",
        )

        assert key_id is not None
        assert api_key.startswith("bob_live_")
        assert len(api_key) > 40

    def test_generate_test_api_key(self, mock_db):
        """Test test environment API key generation"""
        manager = APIKeyManager(mock_db)

        key_id, api_key = manager.generate_api_key(
            user_id="test_user",
            name="Test Key",
            scopes=["repo:read"],
            environment="test",
        )

        assert api_key.startswith("bob_test_")


# ============================================================================
# RBAC Tests
# ============================================================================


class TestRBAC:
    """Tests for role-based access control"""

    def test_get_scopes_for_role(self):
        """Test getting scopes for a role"""
        viewer_scopes = get_scopes_for_role(Role.VIEWER)
        assert Scope.READ_REPOSITORY.value in viewer_scopes
        assert Scope.WRITE_REPOSITORY.value not in viewer_scopes

        admin_scopes = get_scopes_for_role(Role.ADMIN)
        assert Scope.ADMIN_SYSTEM.value in admin_scopes

    @pytest.fixture
    def mock_db(self):
        """Mock database connection"""
        db = Mock()
        cursor = Mock()
        db.cursor.return_value = cursor
        return db

    def test_check_permission(self, mock_db):
        """Test permission checking"""
        checker = AuthorizationChecker(mock_db)

        # User with read permission
        assert checker.check_permission(
            user_scopes=["repo:read"],
            required_scope="repo:read",
        )

        # User without write permission
        assert not checker.check_permission(
            user_scopes=["repo:read"],
            required_scope="repo:write",
        )

        # Admin has all permissions
        assert checker.check_permission(
            user_scopes=["admin:system"],
            required_scope="repo:write",
        )

    def test_check_endpoint_permission(self, mock_db):
        """Test endpoint permission checking"""
        checker = AuthorizationChecker(mock_db)

        # User with code:read can access search
        assert checker.check_endpoint_permission(
            user_scopes=["code:read"],
            endpoint="/api/v1/bob/search",
        )

        # User without code:read cannot access search
        with pytest.raises(AuthorizationError):
            checker.check_endpoint_permission(
                user_scopes=["repo:write"],
                endpoint="/api/v1/bob/search",
            )


# ============================================================================
# Rate Limiter Tests
# ============================================================================


class TestRateLimiter:
    """Tests for rate limiting"""

    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client"""
        redis = Mock()
        redis.zcard.return_value = 0
        redis.zrange.return_value = []
        redis.keys.return_value = []
        redis.get.return_value = None
        return redis

    @pytest.mark.asyncio
    async def test_check_rate_limit_allowed(self, mock_redis):
        """Test rate limit check when allowed"""
        limiter = RateLimiter(mock_redis)

        allowed, metadata = await limiter.check_rate_limit(
            user_id="test_user",
            endpoint="/api/v1/bob/search",
            tier=RateLimitTier.DEVELOPER,
        )

        assert allowed is True
        assert "remaining" in metadata
        assert "reset_at" in metadata

    @pytest.mark.asyncio
    async def test_check_rate_limit_exceeded(self, mock_redis):
        """Test rate limit check when exceeded"""
        # Mock Redis to return high count
        mock_redis.zcard.return_value = 1000

        limiter = RateLimiter(mock_redis)

        with pytest.raises(RateLimitExceededError):
            await limiter.check_rate_limit(
                user_id="test_user",
                endpoint="/api/v1/bob/search",
                tier=RateLimitTier.FREE,
            )

    @pytest.mark.asyncio
    async def test_record_request(self, mock_redis):
        """Test recording a request"""
        limiter = RateLimiter(mock_redis)

        await limiter.record_request(
            user_id="test_user",
            endpoint="/api/v1/bob/search",
            tier=RateLimitTier.DEVELOPER,
        )

        # Verify Redis calls
        assert mock_redis.zadd.called
        assert mock_redis.expire.called


# ============================================================================
# Validation Tests
# ============================================================================


class TestQueryValidator:
    """Tests for query validation"""

    def test_validate_search_query_valid(self):
        """Test validation of valid search query"""
        query = "find authentication function"
        result = QueryValidator.validate_search_query(query)
        assert result == query

    def test_validate_search_query_empty(self):
        """Test validation of empty query"""
        with pytest.raises(InvalidQueryError, match="empty"):
            QueryValidator.validate_search_query("")

    def test_validate_search_query_too_long(self):
        """Test validation of too long query"""
        query = "a" * 1000
        with pytest.raises(InvalidQueryError, match="too long"):
            QueryValidator.validate_search_query(query)

    def test_validate_search_query_sql_injection(self):
        """Test detection of SQL injection patterns"""
        with pytest.raises(InvalidQueryError, match="SQL"):
            QueryValidator.validate_search_query("SELECT * FROM users")

    def test_validate_search_query_script_injection(self):
        """Test detection of script injection"""
        with pytest.raises(InvalidQueryError, match="script"):
            QueryValidator.validate_search_query("<script>alert('xss')</script>")

    def test_validate_file_path_valid(self):
        """Test validation of valid file path"""
        path = "src/app/main.py"
        result = QueryValidator.validate_file_path(path)
        assert result == path

    def test_validate_file_path_traversal(self):
        """Test detection of path traversal"""
        with pytest.raises(InvalidQueryError, match="dangerous"):
            QueryValidator.validate_file_path("../../../etc/passwd")

    def test_validate_file_path_absolute(self):
        """Test rejection of absolute paths"""
        with pytest.raises(InvalidQueryError, match="relative"):
            QueryValidator.validate_file_path("/etc/passwd")

    def test_validate_repo_id_uuid(self):
        """Test validation of UUID repo ID"""
        repo_id = "550e8400-e29b-41d4-a716-446655440000"
        result = QueryValidator.validate_repo_id(repo_id)
        assert result == repo_id

    def test_validate_repo_id_owner_repo(self):
        """Test validation of owner/repo format"""
        repo_id = "owner/repository"
        result = QueryValidator.validate_repo_id(repo_id)
        assert result == repo_id

    def test_validate_repo_id_invalid(self):
        """Test rejection of invalid repo ID"""
        with pytest.raises(InvalidQueryError):
            QueryValidator.validate_repo_id("invalid/repo/format")


class TestRequestValidator:
    """Tests for request parameter validation"""

    def test_validate_pagination_valid(self):
        """Test validation of valid pagination"""
        page, page_size = RequestValidator.validate_pagination(1, 10)
        assert page == 1
        assert page_size == 10

    def test_validate_pagination_invalid_page(self):
        """Test rejection of invalid page number"""
        with pytest.raises(InvalidQueryError):
            RequestValidator.validate_pagination(0, 10)

    def test_validate_pagination_invalid_page_size(self):
        """Test rejection of invalid page size"""
        with pytest.raises(InvalidQueryError):
            RequestValidator.validate_pagination(1, 200)

    def test_validate_hops(self):
        """Test validation of graph traversal hops"""
        assert RequestValidator.validate_hops(3) == 3

        with pytest.raises(InvalidQueryError):
            RequestValidator.validate_hops(20)

    def test_validate_direction(self):
        """Test validation of traversal direction"""
        assert RequestValidator.validate_direction("upstream") == "upstream"
        assert RequestValidator.validate_direction("downstream") == "downstream"
        assert RequestValidator.validate_direction("both") == "both"

        with pytest.raises(InvalidQueryError):
            RequestValidator.validate_direction("invalid")


# ============================================================================
# Secrets Management Tests
# ============================================================================


class TestSecretsManager:
    """Tests for secrets management"""

    def test_encrypt_decrypt_secret(self):
        """Test encryption and decryption"""
        key = generate_encryption_key()
        manager = SecretsManager(key.encode())

        plaintext = "my-secret-value"
        encrypted = manager.encrypt_secret(plaintext)
        decrypted = manager.decrypt_secret(encrypted)

        assert decrypted == plaintext
        assert encrypted != plaintext

    def test_generate_encryption_key(self):
        """Test encryption key generation"""
        key = generate_encryption_key()
        assert isinstance(key, str)
        assert validate_encryption_key(key)

    def test_mask_secret(self):
        """Test secret masking"""
        secret = "bob_live_abcdef123456"
        masked = mask_secret(secret, visible_chars=4)

        assert masked.endswith("3456")
        assert "*" in masked
        assert "abcdef" not in masked

    def test_secret_string(self):
        """Test SecretString wrapper"""
        secret = SecretString("my-secret")

        # Should not expose secret in string representation
        assert str(secret) == "SecretString(****)"
        assert repr(secret) == "SecretString(****)"

        # But should allow getting actual value
        assert secret.get_secret() == "my-secret"

    def test_sanitize_for_logging(self):
        """Test sanitization of sensitive data"""
        data = {
            "username": "user",
            "password": "secret123",
            "api_key": "key123",
            "normal_field": "value",
        }

        sanitized = sanitize_for_logging(data)

        assert sanitized["username"] == "user"
        assert sanitized["password"] == "****"
        assert sanitized["api_key"] == "****"
        assert sanitized["normal_field"] == "value"


# ============================================================================
# Audit Logging Tests
# ============================================================================


class TestAuditLogger:
    """Tests for audit logging"""

    @pytest.fixture
    def mock_db(self):
        """Mock database connection"""
        db = Mock()
        cursor = Mock()
        cursor.fetchone.return_value = ["log_123"]
        db.cursor.return_value = cursor
        return db

    def test_log_event(self, mock_db):
        """Test logging an audit event"""
        logger = AuditLogger(mock_db)

        log_id = logger.log_event(
            event_type=AuditEventType.LOGIN_SUCCESS,
            user_id="test_user",
            resource="authentication",
            action="login",
            result="success",
            metadata={"method": "jwt"},
        )

        assert log_id == "log_123"
        assert mock_db.cursor().execute.called

    def test_log_authentication(self, mock_db):
        """Test logging authentication event"""
        logger = AuditLogger(mock_db)

        log_id = logger.log_authentication(
            user_id="test_user",
            success=True,
            method="jwt",
            ip_address="192.168.1.1",
        )

        assert log_id is not None

    def test_log_data_access(self, mock_db):
        """Test logging data access event"""
        logger = AuditLogger(mock_db)

        log_id = logger.log_data_access(
            user_id="test_user",
            repo_id="repo_123",
            resource_type="file",
            resource_path="src/main.py",
            result_count=1,
        )

        assert log_id is not None


# Made with Bob
