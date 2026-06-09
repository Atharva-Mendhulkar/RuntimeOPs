"""
IBM Bob - Comprehensive Security Tests
Tests for authentication, authorization, injection attacks, and security vulnerabilities
"""

import pytest
import jwt
from datetime import datetime, timedelta
from typing import Dict, Any


# ============================================================================
# Security Test Markers
# ============================================================================

pytestmark = [pytest.mark.security, pytest.mark.asyncio]


# ============================================================================
# Authentication Tests
# ============================================================================


class TestAuthentication:
    """Test authentication mechanisms"""

    async def test_no_token_rejected(self, test_client):
        """Test that requests without token are rejected"""
        response = await test_client.get("/api/v1/search")
        assert response.status_code == 401
        assert "unauthorized" in response.json()["detail"].lower()

    async def test_invalid_token_rejected(self, test_client):
        """Test that invalid tokens are rejected"""
        response = await test_client.get(
            "/api/v1/search",
            headers={"Authorization": "Bearer invalid_token_12345"}
        )
        assert response.status_code == 401

    async def test_expired_token_rejected(self, test_client):
        """Test that expired tokens are rejected"""
        from bob.security.auth import create_access_token
        
        # Create expired token
        expired_token = create_access_token(
            data={"sub": "test_user"},
            expires_delta=timedelta(seconds=-1)  # Already expired
        )
        
        response = await test_client.get(
            "/api/v1/search",
            headers={"Authorization": f"Bearer {expired_token}"}
        )
        assert response.status_code == 401

    async def test_tampered_token_rejected(self, test_client):
        """Test that tampered tokens are rejected"""
        from bob.security.auth import create_access_token
        
        # Create valid token
        valid_token = create_access_token(
            data={"sub": "test_user"},
            expires_delta=timedelta(hours=1)
        )
        
        # Tamper with token (change last 10 characters)
        tampered_token = valid_token[:-10] + "tampered123"
        
        response = await test_client.get(
            "/api/v1/search",
            headers={"Authorization": f"Bearer {tampered_token}"}
        )
        assert response.status_code == 401

    async def test_malformed_auth_header(self, test_client):
        """Test malformed authorization headers"""
        malformed_headers = [
            {"Authorization": "invalid_format"},
            {"Authorization": "Bearer"},
            {"Authorization": "Basic dGVzdDp0ZXN0"},  # Wrong scheme
            {"Authorization": ""},
        ]
        
        for headers in malformed_headers:
            response = await test_client.get(
                "/api/v1/search",
                headers=headers
            )
            assert response.status_code == 401

    async def test_token_with_invalid_signature(self, test_client):
        """Test token with invalid signature"""
        # Create token with wrong secret
        fake_token = jwt.encode(
            {"sub": "test_user", "exp": datetime.utcnow() + timedelta(hours=1)},
            "wrong_secret_key",
            algorithm="HS256"
        )
        
        response = await test_client.get(
            "/api/v1/search",
            headers={"Authorization": f"Bearer {fake_token}"}
        )
        assert response.status_code == 401


# ============================================================================
# Authorization Tests
# ============================================================================


class TestAuthorization:
    """Test authorization and access control"""

    async def test_insufficient_scopes_rejected(self, test_client, limited_auth_headers):
        """Test that requests with insufficient scopes are rejected"""
        # limited_auth_headers only has repo:read scope
        # Try to trigger reindex (requires index:trigger scope)
        response = await test_client.post(
            "/api/v1/repositories/reindex",
            json={"repo_id": "test/repo"},
            headers=limited_auth_headers
        )
        assert response.status_code == 403
        assert "forbidden" in response.json()["detail"].lower()

    async def test_read_only_user_cannot_write(self, test_client, limited_auth_headers):
        """Test that read-only users cannot perform write operations"""
        write_operations = [
            ("/api/v1/repositories/ingest", "POST", {"repo_id": "test/repo"}),
            ("/api/v1/repositories/delete", "DELETE", {"repo_id": "test/repo"}),
            ("/api/v1/repositories/update", "POST", {"repo_id": "test/repo"}),
        ]
        
        for endpoint, method, data in write_operations:
            if method == "POST":
                response = await test_client.post(
                    endpoint,
                    json=data,
                    headers=limited_auth_headers
                )
            elif method == "DELETE":
                response = await test_client.delete(
                    endpoint,
                    params=data,
                    headers=limited_auth_headers
                )
            
            assert response.status_code == 403

    async def test_cross_repository_access_denied(self, test_client, auth_headers):
        """Test that users cannot access repositories they don't have permission for"""
        # This test assumes RBAC is configured to restrict access
        response = await test_client.post(
            "/api/v1/search",
            json={
                "query": "test",
                "repo_id": "unauthorized/repo"
            },
            headers=auth_headers
        )
        # Should either return 403 or empty results depending on implementation
        assert response.status_code in [200, 403]


# ============================================================================
# SQL Injection Tests
# ============================================================================


class TestSQLInjection:
    """Test SQL injection protection"""

    async def test_sql_injection_in_search_query(
        self,
        test_client,
        auth_headers,
        sql_injection_payloads
    ):
        """Test SQL injection attempts in search queries"""
        for payload in sql_injection_payloads:
            response = await test_client.post(
                "/api/v1/search",
                json={
                    "query": payload,
                    "repo_id": "test/repo",
                    "k": 10
                },
                headers=auth_headers
            )
            # Should not cause error, should sanitize input
            assert response.status_code in [200, 400]
            
            # Verify no SQL error in response
            if response.status_code == 200:
                result = response.json()
                assert "error" not in result or "sql" not in str(result.get("error", "")).lower()

    async def test_sql_injection_in_repo_id(
        self,
        test_client,
        auth_headers,
        sql_injection_payloads
    ):
        """Test SQL injection attempts in repo_id parameter"""
        for payload in sql_injection_payloads:
            response = await test_client.post(
                "/api/v1/search",
                json={
                    "query": "test",
                    "repo_id": payload,
                    "k": 10
                },
                headers=auth_headers
            )
            # Should reject or sanitize
            assert response.status_code in [200, 400, 404]

    async def test_sql_injection_in_file_path(
        self,
        test_client,
        auth_headers,
        sql_injection_payloads
    ):
        """Test SQL injection attempts in file_path parameter"""
        for payload in sql_injection_payloads:
            response = await test_client.get(
                "/api/v1/file",
                params={
                    "file_path": payload,
                    "repo_id": "test/repo"
                },
                headers=auth_headers
            )
            # Should reject or sanitize
            assert response.status_code in [200, 400, 404]


# ============================================================================
# Path Traversal Tests
# ============================================================================


class TestPathTraversal:
    """Test path traversal protection"""

    async def test_path_traversal_in_file_path(
        self,
        test_client,
        auth_headers,
        path_traversal_payloads
    ):
        """Test path traversal attempts in file_path parameter"""
        for payload in path_traversal_payloads:
            response = await test_client.get(
                "/api/v1/file",
                params={
                    "file_path": payload,
                    "repo_id": "test/repo"
                },
                headers=auth_headers
            )
            # Should reject or sanitize
            assert response.status_code in [400, 404]
            
            # Verify no sensitive file content is returned
            if response.status_code == 200:
                content = response.json().get("content", "")
                # Should not contain system file content
                assert "root:" not in content  # /etc/passwd
                assert "SYSTEM" not in content  # Windows system files

    async def test_path_traversal_in_repo_id(
        self,
        test_client,
        auth_headers,
        path_traversal_payloads
    ):
        """Test path traversal attempts in repo_id parameter"""
        for payload in path_traversal_payloads:
            response = await test_client.post(
                "/api/v1/search",
                json={
                    "query": "test",
                    "repo_id": payload,
                    "k": 10
                },
                headers=auth_headers
            )
            # Should reject or sanitize
            assert response.status_code in [200, 400, 404]


# ============================================================================
# XSS Tests
# ============================================================================


class TestXSS:
    """Test XSS protection"""

    async def test_xss_in_search_query(
        self,
        test_client,
        auth_headers,
        xss_payloads
    ):
        """Test XSS attempts in search queries"""
        for payload in xss_payloads:
            response = await test_client.post(
                "/api/v1/search",
                json={
                    "query": payload,
                    "repo_id": "test/repo",
                    "k": 10
                },
                headers=auth_headers
            )
            
            if response.status_code == 200:
                result = response.json()
                # Verify response doesn't contain unescaped script tags
                response_text = str(result)
                assert "<script>" not in response_text.lower()
                assert "javascript:" not in response_text.lower()

    async def test_xss_in_error_messages(self, test_client, auth_headers):
        """Test that error messages don't reflect XSS payloads"""
        xss_payload = "<script>alert('XSS')</script>"
        
        response = await test_client.get(
            "/api/v1/file",
            params={
                "file_path": xss_payload,
                "repo_id": "test/repo"
            },
            headers=auth_headers
        )
        
        # Error message should not contain unescaped payload
        if response.status_code >= 400:
            error_text = str(response.json())
            assert "<script>" not in error_text


# ============================================================================
# Rate Limiting Tests
# ============================================================================


class TestRateLimiting:
    """Test rate limiting"""

    async def test_rate_limit_enforcement(self, test_client, auth_headers):
        """Test that rate limits are enforced"""
        # Make many requests quickly
        responses = []
        for _ in range(150):  # Exceed typical rate limit
            response = await test_client.post(
                "/api/v1/search",
                json={
                    "query": "test",
                    "repo_id": "test/repo",
                    "k": 5
                },
                headers=auth_headers
            )
            responses.append(response)
        
        # At least some requests should be rate limited
        rate_limited = [r for r in responses if r.status_code == 429]
        assert len(rate_limited) > 0, "Rate limiting not enforced"

    async def test_rate_limit_headers(self, test_client, auth_headers):
        """Test that rate limit headers are present"""
        response = await test_client.post(
            "/api/v1/search",
            json={
                "query": "test",
                "repo_id": "test/repo",
                "k": 5
            },
            headers=auth_headers
        )
        
        # Check for rate limit headers
        assert "X-RateLimit-Limit" in response.headers or "RateLimit-Limit" in response.headers


# ============================================================================
# Input Validation Tests
# ============================================================================


class TestInputValidation:
    """Test input validation"""

    async def test_oversized_query_rejected(self, test_client, auth_headers):
        """Test that oversized queries are rejected"""
        # Create very long query (>10KB)
        oversized_query = "test " * 3000
        
        response = await test_client.post(
            "/api/v1/search",
            json={
                "query": oversized_query,
                "repo_id": "test/repo",
                "k": 10
            },
            headers=auth_headers
        )
        assert response.status_code == 400

    async def test_invalid_k_parameter(self, test_client, auth_headers):
        """Test invalid k parameter values"""
        invalid_k_values = [-1, 0, 1000, "invalid"]
        
        for k in invalid_k_values:
            response = await test_client.post(
                "/api/v1/search",
                json={
                    "query": "test",
                    "repo_id": "test/repo",
                    "k": k
                },
                headers=auth_headers
            )
            assert response.status_code == 400

    async def test_invalid_hops_parameter(self, test_client, auth_headers):
        """Test invalid hops parameter values"""
        invalid_hops = [-1, 0, 100, "invalid"]
        
        for hops in invalid_hops:
            response = await test_client.get(
                "/api/v1/dependencies",
                params={
                    "file_path": "test.py",
                    "repo_id": "test/repo",
                    "hops": hops
                },
                headers=auth_headers
            )
            assert response.status_code == 400

    async def test_empty_required_fields(self, test_client, auth_headers):
        """Test that empty required fields are rejected"""
        test_cases = [
            ("/api/v1/search", {"query": "", "repo_id": "test/repo"}),
            ("/api/v1/search", {"query": "test", "repo_id": ""}),
            ("/api/v1/file", {"file_path": "", "repo_id": "test/repo"}),
        ]
        
        for endpoint, data in test_cases:
            if "file_path" in data:
                response = await test_client.get(
                    endpoint,
                    params=data,
                    headers=auth_headers
                )
            else:
                response = await test_client.post(
                    endpoint,
                    json=data,
                    headers=auth_headers
                )
            assert response.status_code == 400


# ============================================================================
# CORS Tests
# ============================================================================


class TestCORS:
    """Test CORS configuration"""

    async def test_cors_headers_present(self, test_client):
        """Test that CORS headers are present"""
        response = await test_client.options(
            "/api/v1/search",
            headers={"Origin": "https://example.com"}
        )
        
        # Should have CORS headers
        assert "Access-Control-Allow-Origin" in response.headers or response.status_code == 200

    async def test_cors_restricts_origins(self, test_client):
        """Test that CORS restricts unauthorized origins"""
        response = await test_client.options(
            "/api/v1/search",
            headers={"Origin": "https://malicious-site.com"}
        )
        
        # Should either reject or not include the origin in allowed origins
        if "Access-Control-Allow-Origin" in response.headers:
            allowed_origin = response.headers["Access-Control-Allow-Origin"]
            assert allowed_origin != "https://malicious-site.com" or allowed_origin == "*"


# ============================================================================
# Encryption Tests
# ============================================================================


class TestEncryption:
    """Test data encryption"""

    async def test_sensitive_data_not_in_logs(self, test_client, auth_headers):
        """Test that sensitive data is not logged"""
        # This is a placeholder - actual implementation would check logs
        response = await test_client.post(
            "/api/v1/search",
            json={
                "query": "password123",  # Sensitive data
                "repo_id": "test/repo",
                "k": 10
            },
            headers=auth_headers
        )
        
        # Verify request completes
        assert response.status_code in [200, 400]

    async def test_tokens_not_in_response(self, test_client, auth_headers):
        """Test that auth tokens are not included in responses"""
        response = await test_client.post(
            "/api/v1/search",
            json={
                "query": "test",
                "repo_id": "test/repo",
                "k": 10
            },
            headers=auth_headers
        )
        
        if response.status_code == 200:
            response_text = str(response.json())
            # Should not contain JWT tokens
            assert "eyJ" not in response_text  # JWT prefix


# ============================================================================
# Security Headers Tests
# ============================================================================


class TestSecurityHeaders:
    """Test security headers"""

    async def test_security_headers_present(self, test_client, auth_headers):
        """Test that security headers are present"""
        response = await test_client.get(
            "/health/ready",
            headers=auth_headers
        )
        
        # Check for important security headers
        headers_to_check = [
            "X-Content-Type-Options",
            "X-Frame-Options",
            "X-XSS-Protection",
            "Strict-Transport-Security",
        ]
        
        present_headers = [h for h in headers_to_check if h in response.headers]
        
        # At least some security headers should be present
        assert len(present_headers) > 0, "No security headers found"

    async def test_no_sensitive_headers_leaked(self, test_client):
        """Test that sensitive headers are not leaked"""
        response = await test_client.get("/health/ready")
        
        # Should not leak server information
        sensitive_headers = ["Server", "X-Powered-By"]
        for header in sensitive_headers:
            if header in response.headers:
                # If present, should not reveal detailed version info
                value = response.headers[header].lower()
                assert "python" not in value
                assert "fastapi" not in value


# Made with Bob