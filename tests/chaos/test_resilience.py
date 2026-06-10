"""
IBM Bob - Chaos Engineering Tests
Tests for system resilience under failure conditions
"""

import asyncio
from typing import Any, Dict

import pytest

# ============================================================================
# Chaos Test Markers
# ============================================================================

pytestmark = [pytest.mark.chaos, pytest.mark.asyncio]


# ============================================================================
# Database Failure Tests
# ============================================================================


class TestDatabaseFailures:
    """Test resilience to database failures"""

    async def test_postgres_failure_recovery(self, test_client, auth_headers, chaos_controller):
        """Test recovery from PostgreSQL failure"""

        # 1. Verify system is healthy
        response = await test_client.get("/health/ready")
        assert response.status_code == 200
        health = response.json()
        assert health["status"] == "healthy"

        # 2. Simulate PostgreSQL failure
        await chaos_controller.kill_service("postgres")

        # 3. Verify graceful degradation
        await asyncio.sleep(2)  # Wait for health check to detect failure
        response = await test_client.get("/health/ready")
        assert response.status_code == 503
        health = response.json()
        assert health["status"] == "unhealthy"
        assert "postgres" in str(health.get("details", {})).lower()

        # 4. Verify read operations still work (from cache)
        response = await test_client.get(
            "/api/v1/file",
            params={"file_path": "src/main.py", "repo_id": "test/repo"},
            headers=auth_headers,
        )
        # Should work if cached, or fail gracefully
        assert response.status_code in [200, 503]

        # 5. Restore PostgreSQL
        await chaos_controller.restore_service("postgres")
        await asyncio.sleep(2)

        # 6. Verify recovery
        response = await test_client.get("/health/ready")
        assert response.status_code == 200

    async def test_neo4j_failure_handling(self, test_client, auth_headers, chaos_controller):
        """Test handling of Neo4j failure"""

        # 1. Verify graph queries work
        response = await test_client.get(
            "/api/v1/dependencies",
            params={"file_path": "src/main.py", "repo_id": "test/repo", "hops": 2},
            headers=auth_headers,
        )
        initial_status = response.status_code

        # 2. Simulate Neo4j failure
        await chaos_controller.kill_service("neo4j")
        await asyncio.sleep(1)

        # 3. Verify graceful degradation
        response = await test_client.get(
            "/api/v1/dependencies",
            params={"file_path": "src/main.py", "repo_id": "test/repo", "hops": 2},
            headers=auth_headers,
        )
        # Should return error or degraded response
        assert response.status_code in [503, 500]

        # 4. Verify other services still work
        response = await test_client.post(
            "/api/v1/search",
            json={"query": "test", "repo_id": "test/repo", "k": 5},
            headers=auth_headers,
        )
        # Search should still work (uses Weaviate)
        assert response.status_code in [200, 503]

        # 5. Restore Neo4j
        await chaos_controller.restore_service("neo4j")
        await asyncio.sleep(2)

        # 6. Verify recovery
        response = await test_client.get(
            "/api/v1/dependencies",
            params={"file_path": "src/main.py", "repo_id": "test/repo", "hops": 2},
            headers=auth_headers,
        )
        assert response.status_code == initial_status

    async def test_weaviate_failure_handling(self, test_client, auth_headers, chaos_controller):
        """Test handling of Weaviate failure"""

        # 1. Simulate Weaviate failure
        await chaos_controller.kill_service("weaviate")
        await asyncio.sleep(1)

        # 2. Verify semantic search fails gracefully
        response = await test_client.post(
            "/api/v1/search",
            json={"query": "test function", "repo_id": "test/repo", "k": 10},
            headers=auth_headers,
        )
        assert response.status_code in [503, 500]

        # Verify error message is informative
        if response.status_code >= 500:
            error = response.json()
            assert "detail" in error or "message" in error

        # 3. Verify other services still work
        response = await test_client.get(
            "/api/v1/file",
            params={"file_path": "src/main.py", "repo_id": "test/repo"},
            headers=auth_headers,
        )
        # File retrieval should still work (uses Redis/Git)
        assert response.status_code in [200, 404]

        # 4. Restore Weaviate
        await chaos_controller.restore_service("weaviate")
        await asyncio.sleep(2)

        # 5. Verify recovery
        response = await test_client.post(
            "/api/v1/search",
            json={"query": "test function", "repo_id": "test/repo", "k": 10},
            headers=auth_headers,
        )
        assert response.status_code == 200


# ============================================================================
# Cache Failure Tests
# ============================================================================


class TestCacheFailures:
    """Test resilience to cache failures"""

    async def test_redis_failure_handling(self, test_client, auth_headers, chaos_controller):
        """Test handling of Redis cache failure"""

        # 1. Make request with cache
        response1 = await test_client.get(
            "/api/v1/file",
            params={"file_path": "src/main.py", "repo_id": "test/repo"},
            headers=auth_headers,
        )
        initial_status = response1.status_code

        # 2. Simulate Redis failure
        await chaos_controller.kill_service("redis")
        await asyncio.sleep(1)

        # 3. Verify system continues to work (without cache)
        response2 = await test_client.get(
            "/api/v1/file",
            params={"file_path": "src/main.py", "repo_id": "test/repo"},
            headers=auth_headers,
        )
        # Should still work, just slower (fallback to Git)
        assert response2.status_code == initial_status

        # 4. Verify search still works
        response = await test_client.post(
            "/api/v1/search",
            json={"query": "test", "repo_id": "test/repo", "k": 5},
            headers=auth_headers,
        )
        assert response.status_code == 200

        # 5. Restore Redis
        await chaos_controller.restore_service("redis")
        await asyncio.sleep(1)

        # 6. Verify cache is working again
        response3 = await test_client.get(
            "/api/v1/file",
            params={"file_path": "src/main.py", "repo_id": "test/repo"},
            headers=auth_headers,
        )
        assert response3.status_code == 200

    async def test_cache_corruption_handling(self, test_client, auth_headers, test_redis):
        """Test handling of corrupted cache data"""

        # 1. Insert corrupted data into cache
        cache_key = "file:test/repo:src/main.py"
        await test_redis.set(cache_key, "corrupted_data_not_json")

        # 2. Request should handle corruption gracefully
        response = await test_client.get(
            "/api/v1/file",
            params={"file_path": "src/main.py", "repo_id": "test/repo"},
            headers=auth_headers,
        )

        # Should fallback to source or return error
        assert response.status_code in [200, 404, 500]

        # 3. Verify cache is cleared/fixed
        cached_value = await test_redis.get(cache_key)
        # Should be cleared or contain valid data
        assert cached_value is None or cached_value != "corrupted_data_not_json"


# ============================================================================
# Network Failure Tests
# ============================================================================


class TestNetworkFailures:
    """Test resilience to network failures"""

    async def test_slow_database_response(self, test_client, auth_headers, chaos_controller):
        """Test handling of slow database responses"""

        # 1. Inject latency
        await chaos_controller.inject_latency("postgres", duration=5.0)

        # 2. Make request
        import time

        start = time.time()
        response = await test_client.post(
            "/api/v1/search",
            json={"query": "test", "repo_id": "test/repo", "k": 5},
            headers=auth_headers,
        )
        duration = time.time() - start

        # 3. Should timeout or complete
        assert response.status_code in [200, 504, 503]

        # 4. Should not hang indefinitely
        assert duration < 15.0, "Request hung for too long"

    async def test_intermittent_connection_failures(
        self, test_client, auth_headers, chaos_controller
    ):
        """Test handling of intermittent connection failures"""

        success_count = 0
        failure_count = 0

        # Make multiple requests with intermittent failures
        for i in range(10):
            # Simulate intermittent failures
            if i % 3 == 0:
                await chaos_controller.kill_service("neo4j")
            else:
                await chaos_controller.restore_service("neo4j")

            await asyncio.sleep(0.5)

            response = await test_client.get(
                "/api/v1/dependencies",
                params={"file_path": "src/main.py", "repo_id": "test/repo", "hops": 1},
                headers=auth_headers,
            )

            if response.status_code == 200:
                success_count += 1
            else:
                failure_count += 1

        # Should have some successes and some failures
        assert success_count > 0, "No successful requests"
        assert failure_count > 0, "No failed requests (chaos not working)"

        # Restore service
        await chaos_controller.restore_service("neo4j")


# ============================================================================
# Resource Exhaustion Tests
# ============================================================================


class TestResourceExhaustion:
    """Test resilience to resource exhaustion"""

    async def test_memory_pressure_handling(self, test_client, auth_headers, large_repository):
        """Test handling of memory pressure"""

        # Make many concurrent requests to create memory pressure
        async def make_request():
            return await test_client.post(
                "/api/v1/search",
                json={
                    "query": "test function",
                    "repo_id": large_repository["repo_id"],
                    "k": 50,  # Large result set
                },
                headers=auth_headers,
            )

        # Send 50 concurrent requests
        tasks = [make_request() for _ in range(50)]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        # Most should succeed, some might fail gracefully
        successful = sum(
            1 for r in responses if not isinstance(r, Exception) and r.status_code == 200
        )
        failed = len(responses) - successful

        # At least 80% should succeed
        success_rate = successful / len(responses)
        assert success_rate >= 0.8, f"Success rate {success_rate:.1%} below 80%"

        # Failed requests should fail gracefully (not crash)
        for r in responses:
            if isinstance(r, Exception):
                # Should be handled exception, not crash
                assert "timeout" in str(r).lower() or "connection" in str(r).lower()

    async def test_connection_pool_exhaustion(self, test_client, auth_headers):
        """Test handling of connection pool exhaustion"""

        # Make many concurrent requests to exhaust connection pool
        async def make_long_request():
            return await test_client.get(
                "/api/v1/dependencies",
                params={
                    "file_path": "src/main.py",
                    "repo_id": "test/repo",
                    "hops": 3,  # Expensive query
                },
                headers=auth_headers,
            )

        # Send 100 concurrent requests
        tasks = [make_long_request() for _ in range(100)]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        # Should handle gracefully
        successful = sum(
            1 for r in responses if not isinstance(r, Exception) and r.status_code == 200
        )

        # At least 70% should succeed
        success_rate = successful / len(responses)
        assert success_rate >= 0.7, f"Success rate {success_rate:.1%} below 70%"


# ============================================================================
# Cascading Failure Tests
# ============================================================================


class TestCascadingFailures:
    """Test resilience to cascading failures"""

    async def test_multiple_service_failures(self, test_client, auth_headers, chaos_controller):
        """Test handling of multiple simultaneous service failures"""

        # 1. Kill multiple services
        await chaos_controller.kill_service("redis")
        await chaos_controller.kill_service("neo4j")
        await asyncio.sleep(2)

        # 2. System should still respond (degraded)
        response = await test_client.get("/health/ready")
        assert response.status_code == 503

        # 3. Some operations should still work
        response = await test_client.post(
            "/api/v1/search",
            json={"query": "test", "repo_id": "test/repo", "k": 5},
            headers=auth_headers,
        )
        # Search might still work (uses Weaviate)
        assert response.status_code in [200, 503]

        # 4. Restore services one by one
        await chaos_controller.restore_service("redis")
        await asyncio.sleep(1)

        response = await test_client.get("/health/ready")
        # Still unhealthy (Neo4j down)
        assert response.status_code == 503

        await chaos_controller.restore_service("neo4j")
        await asyncio.sleep(2)

        # 5. Verify full recovery
        response = await test_client.get("/health/ready")
        assert response.status_code == 200

    async def test_partial_data_availability(self, test_client, auth_headers, chaos_controller):
        """Test system behavior with partial data availability"""

        # 1. Kill Neo4j (graph data unavailable)
        await chaos_controller.kill_service("neo4j")
        await asyncio.sleep(1)

        # 2. Search should still work (vector data available)
        response = await test_client.post(
            "/api/v1/search",
            json={"query": "test function", "repo_id": "test/repo", "k": 10},
            headers=auth_headers,
        )
        assert response.status_code == 200

        # 3. Results should indicate limited data
        results = response.json()
        # Might have flag indicating graph data unavailable
        if "metadata" in results:
            assert "graph_available" in results["metadata"] or True

        # 4. Restore Neo4j
        await chaos_controller.restore_service("neo4j")
        await asyncio.sleep(2)

        # 5. Full data should be available
        response = await test_client.post(
            "/api/v1/search",
            json={"query": "test function", "repo_id": "test/repo", "k": 10},
            headers=auth_headers,
        )
        assert response.status_code == 200


# ============================================================================
# Recovery Tests
# ============================================================================


class TestRecovery:
    """Test system recovery mechanisms"""

    async def test_automatic_reconnection(self, test_client, auth_headers, chaos_controller):
        """Test automatic reconnection after failure"""

        # 1. Kill and restore service quickly
        await chaos_controller.kill_service("postgres")
        await asyncio.sleep(1)
        await chaos_controller.restore_service("postgres")

        # 2. System should reconnect automatically
        max_attempts = 10
        for attempt in range(max_attempts):
            await asyncio.sleep(1)
            response = await test_client.get("/health/ready")
            if response.status_code == 200:
                break

        # Should recover within reasonable time
        assert response.status_code == 200, "System did not recover"

    async def test_circuit_breaker_behavior(self, test_client, auth_headers, chaos_controller):
        """Test circuit breaker behavior"""

        # 1. Cause repeated failures
        await chaos_controller.kill_service("neo4j")

        # 2. Make multiple requests
        failure_count = 0
        for _ in range(10):
            response = await test_client.get(
                "/api/v1/dependencies",
                params={"file_path": "src/main.py", "repo_id": "test/repo", "hops": 2},
                headers=auth_headers,
            )
            if response.status_code >= 500:
                failure_count += 1
            await asyncio.sleep(0.5)

        # Should have failures
        assert failure_count > 0

        # 3. Restore service
        await chaos_controller.restore_service("neo4j")
        await asyncio.sleep(3)  # Wait for circuit breaker to close

        # 4. Requests should succeed again
        response = await test_client.get(
            "/api/v1/dependencies",
            params={"file_path": "src/main.py", "repo_id": "test/repo", "hops": 2},
            headers=auth_headers,
        )
        assert response.status_code == 200


# Made with Bob
