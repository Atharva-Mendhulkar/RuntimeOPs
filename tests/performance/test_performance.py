"""
IBM Bob - Performance Benchmarking Tests
Tests for query performance, ingestion throughput, and system scalability
"""

import asyncio
import pytest
import time
from statistics import mean, median, stdev
from typing import List, Dict, Any


# ============================================================================
# Performance Test Markers
# ============================================================================

pytestmark = [pytest.mark.performance, pytest.mark.asyncio]


# ============================================================================
# Query Performance Tests
# ============================================================================


class TestQueryPerformance:
    """Test query performance benchmarks"""

    async def test_semantic_search_performance(
        self,
        test_client,
        auth_headers,
        large_repository,
        performance_tracker,
    ):
        """Test semantic search performance under load"""
        
        # Ingest large repository first
        ingest_response = await test_client.post(
            "/api/v1/repositories/ingest",
            json={"repo_id": large_repository["repo_id"]},
            headers=auth_headers
        )
        job_id = ingest_response.json()["job_id"]
        await self._wait_for_job(test_client, job_id, auth_headers, timeout=300)
        
        # Test queries
        queries = [
            "authentication function",
            "database connection",
            "error handling",
            "API endpoint",
            "data validation",
            "logging utility",
            "configuration parser",
            "cache manager",
            "request handler",
            "response formatter"
        ]
        
        latencies = []
        
        for query in queries:
            start = time.time()
            response = await test_client.post(
                "/api/v1/search",
                json={
                    "query": query,
                    "repo_id": large_repository["repo_id"],
                    "k": 10
                },
                headers=auth_headers
            )
            latency = time.time() - start
            latencies.append(latency)
            
            assert response.status_code == 200
            performance_tracker.record("semantic_search", latency, query=query)
        
        # Performance assertions
        avg_latency = mean(latencies)
        median_latency = median(latencies)
        p95_latency = sorted(latencies)[int(len(latencies) * 0.95)]
        p99_latency = sorted(latencies)[int(len(latencies) * 0.99)]
        
        print(f"\nSemantic Search Performance:")
        print(f"  Average: {avg_latency:.3f}s")
        print(f"  Median: {median_latency:.3f}s")
        print(f"  P95: {p95_latency:.3f}s")
        print(f"  P99: {p99_latency:.3f}s")
        
        # SLA assertions (from PRD)
        assert avg_latency < 1.0, f"Average latency {avg_latency:.3f}s exceeds 1.0s"
        assert median_latency < 0.8, f"Median latency {median_latency:.3f}s exceeds 0.8s"
        assert p95_latency < 2.0, f"P95 latency {p95_latency:.3f}s exceeds 2.0s"

    async def test_graph_query_performance(
        self,
        test_client,
        auth_headers,
        large_repository,
        performance_tracker,
    ):
        """Test graph query performance"""
        
        # Ingest repository
        ingest_response = await test_client.post(
            "/api/v1/repositories/ingest",
            json={"repo_id": large_repository["repo_id"]},
            headers=auth_headers
        )
        job_id = ingest_response.json()["job_id"]
        await self._wait_for_job(test_client, job_id, auth_headers, timeout=300)
        
        # Test different graph operations
        test_cases = [
            {
                "operation": "dependencies",
                "params": {
                    "file_path": "src/module_0.py",
                    "repo_id": large_repository["repo_id"],
                    "hops": 2
                },
                "max_latency": 0.4  # 400ms
            },
            {
                "operation": "dependencies",
                "params": {
                    "file_path": "src/module_0.py",
                    "repo_id": large_repository["repo_id"],
                    "hops": 3
                },
                "max_latency": 0.6  # 600ms
            }
        ]
        
        for test_case in test_cases:
            start = time.time()
            response = await test_client.get(
                "/api/v1/dependencies",
                params=test_case["params"],
                headers=auth_headers
            )
            latency = time.time() - start
            
            assert response.status_code == 200
            performance_tracker.record(
                "graph_query",
                latency,
                operation=test_case["operation"],
                hops=test_case["params"]["hops"]
            )
            
            print(f"\nGraph Query ({test_case['params']['hops']} hops): {latency:.3f}s")
            assert latency < test_case["max_latency"], \
                f"Latency {latency:.3f}s exceeds {test_case['max_latency']}s"

    async def test_file_retrieval_performance(
        self,
        test_client,
        auth_headers,
        large_repository,
        performance_tracker,
    ):
        """Test file retrieval performance (cache hit/miss)"""
        
        # Ingest repository
        ingest_response = await test_client.post(
            "/api/v1/repositories/ingest",
            json={"repo_id": large_repository["repo_id"]},
            headers=auth_headers
        )
        job_id = ingest_response.json()["job_id"]
        await self._wait_for_job(test_client, job_id, auth_headers, timeout=300)
        
        file_path = "src/module_0.py"
        
        # First request (cache miss)
        start = time.time()
        response = await test_client.get(
            "/api/v1/file",
            params={
                "file_path": file_path,
                "repo_id": large_repository["repo_id"]
            },
            headers=auth_headers
        )
        cache_miss_latency = time.time() - start
        assert response.status_code == 200
        
        # Second request (cache hit)
        start = time.time()
        response = await test_client.get(
            "/api/v1/file",
            params={
                "file_path": file_path,
                "repo_id": large_repository["repo_id"]
            },
            headers=auth_headers
        )
        cache_hit_latency = time.time() - start
        assert response.status_code == 200
        
        print(f"\nFile Retrieval Performance:")
        print(f"  Cache Miss: {cache_miss_latency:.3f}s")
        print(f"  Cache Hit: {cache_hit_latency:.3f}s")
        print(f"  Speedup: {cache_miss_latency / cache_hit_latency:.1f}x")
        
        # Cache hit should be significantly faster
        assert cache_hit_latency < 0.05, f"Cache hit latency {cache_hit_latency:.3f}s exceeds 50ms"
        assert cache_hit_latency < cache_miss_latency / 2, "Cache hit not significantly faster"

    async def _wait_for_job(self, test_client, job_id: str, auth_headers: Dict[str, str], timeout: int = 30):
        """Helper to wait for job completion"""
        for _ in range(timeout):
            response = await test_client.get(
                f"/api/v1/jobs/{job_id}",
                headers=auth_headers
            )
            status = response.json()["status"]
            if status == "completed":
                return
            elif status == "failed":
                pytest.fail(f"Job {job_id} failed")
            await asyncio.sleep(1)
        pytest.fail(f"Job {job_id} did not complete within {timeout} seconds")


# ============================================================================
# Ingestion Performance Tests
# ============================================================================


class TestIngestionPerformance:
    """Test repository ingestion performance"""

    async def test_repository_ingestion_performance(
        self,
        test_client,
        auth_headers,
        performance_tracker,
    ):
        """Test repository ingestion performance at different scales"""
        
        test_cases = [
            {"files": 10, "max_time": 30, "name": "small"},
            {"files": 100, "max_time": 120, "name": "medium"},
            {"files": 500, "max_time": 300, "name": "large"}
        ]
        
        for case in test_cases:
            # Generate test repository
            repo = self._generate_test_repository(
                num_files=case["files"],
                repo_name=f"perf-test-{case['name']}"
            )
            
            start = time.time()
            
            # Trigger ingestion
            response = await test_client.post(
                "/api/v1/repositories/ingest",
                json={"repo_id": repo["repo_id"]},
                headers=auth_headers
            )
            assert response.status_code == 202
            job_id = response.json()["job_id"]
            
            # Wait for completion
            await self._wait_for_job(test_client, job_id, auth_headers, timeout=case["max_time"])
            
            duration = time.time() - start
            
            # Calculate throughput
            total_lines = case["files"] * 20  # Assume 20 lines per file
            throughput = total_lines / duration  # Lines per second
            
            print(f"\nIngestion Performance ({case['name']}):")
            print(f"  Files: {case['files']}")
            print(f"  Duration: {duration:.1f}s")
            print(f"  Throughput: {throughput:.0f} lines/sec")
            
            performance_tracker.record(
                "ingestion",
                duration,
                files=case["files"],
                throughput=throughput
            )
            
            assert duration < case["max_time"], \
                f"Ingestion took {duration:.1f}s, exceeds {case['max_time']}s"

    async def test_incremental_update_performance(
        self,
        test_client,
        auth_headers,
        large_repository,
    ):
        """Test incremental update performance"""
        
        # Initial ingestion
        response = await test_client.post(
            "/api/v1/repositories/ingest",
            json={"repo_id": large_repository["repo_id"]},
            headers=auth_headers
        )
        job_id = response.json()["job_id"]
        await self._wait_for_job(test_client, job_id, auth_headers, timeout=300)
        
        # Incremental update (simulating 10 file changes)
        start = time.time()
        response = await test_client.post(
            "/api/v1/repositories/update",
            json={
                "repo_id": large_repository["repo_id"],
                "commit_sha": "abc123",
                "changed_files": [f"src/module_{i}.py" for i in range(10)]
            },
            headers=auth_headers
        )
        job_id = response.json()["job_id"]
        await self._wait_for_job(test_client, job_id, auth_headers, timeout=60)
        
        duration = time.time() - start
        
        print(f"\nIncremental Update Performance:")
        print(f"  Changed Files: 10")
        print(f"  Duration: {duration:.1f}s")
        
        # Incremental update should be much faster than full reindex
        assert duration < 60, f"Incremental update took {duration:.1f}s, exceeds 60s"

    def _generate_test_repository(self, num_files: int, repo_name: str) -> Dict[str, Any]:
        """Generate test repository with specified number of files"""
        files = []
        for i in range(num_files):
            files.append({
                "path": f"src/file_{i}.py",
                "content": f"""def function_{i}():
    '''Function {i}'''
    return {i}

class Class_{i}:
    '''Class {i}'''
    pass
""",
                "language": "python"
            })
        
        return {
            "repo_id": f"test/{repo_name}",
            "owner": "test",
            "name": repo_name,
            "default_branch": "main",
            "files": files
        }

    async def _wait_for_job(self, test_client, job_id: str, auth_headers: Dict[str, str], timeout: int = 30):
        """Helper to wait for job completion"""
        for _ in range(timeout):
            response = await test_client.get(
                f"/api/v1/jobs/{job_id}",
                headers=auth_headers
            )
            status = response.json()["status"]
            if status == "completed":
                return
            elif status == "failed":
                pytest.fail(f"Job {job_id} failed")
            await asyncio.sleep(1)
        pytest.fail(f"Job {job_id} did not complete within {timeout} seconds")


# ============================================================================
# Concurrent Request Handling Tests
# ============================================================================


class TestConcurrentPerformance:
    """Test system performance under concurrent load"""

    async def test_concurrent_search_requests(
        self,
        test_client,
        auth_headers,
        large_repository,
        performance_tracker,
    ):
        """Test system under concurrent search load"""
        
        # Ingest repository
        ingest_response = await test_client.post(
            "/api/v1/repositories/ingest",
            json={"repo_id": large_repository["repo_id"]},
            headers=auth_headers
        )
        job_id = ingest_response.json()["job_id"]
        await self._wait_for_job(test_client, job_id, auth_headers, timeout=300)
        
        async def make_search_request():
            """Make a single search request"""
            start = time.time()
            response = await test_client.post(
                "/api/v1/search",
                json={
                    "query": "test function",
                    "repo_id": large_repository["repo_id"],
                    "k": 10
                },
                headers=auth_headers
            )
            latency = time.time() - start
            return response.status_code, latency
        
        # Send 100 concurrent requests
        num_requests = 100
        start = time.time()
        tasks = [make_search_request() for _ in range(num_requests)]
        results = await asyncio.gather(*tasks)
        total_duration = time.time() - start
        
        # Analyze results
        status_codes = [r[0] for r in results]
        latencies = [r[1] for r in results]
        
        success_count = sum(1 for code in status_codes if code == 200)
        success_rate = success_count / num_requests
        
        avg_latency = mean(latencies)
        p95_latency = sorted(latencies)[int(len(latencies) * 0.95)]
        throughput = num_requests / total_duration
        
        print(f"\nConcurrent Search Performance:")
        print(f"  Requests: {num_requests}")
        print(f"  Success Rate: {success_rate:.1%}")
        print(f"  Total Duration: {total_duration:.1f}s")
        print(f"  Throughput: {throughput:.1f} req/s")
        print(f"  Avg Latency: {avg_latency:.3f}s")
        print(f"  P95 Latency: {p95_latency:.3f}s")
        
        # Performance assertions
        assert success_rate >= 0.95, f"Success rate {success_rate:.1%} below 95%"
        assert avg_latency < 2.0, f"Average latency {avg_latency:.3f}s exceeds 2.0s"
        assert throughput > 10, f"Throughput {throughput:.1f} req/s below 10 req/s"

    async def test_mixed_workload_performance(
        self,
        test_client,
        auth_headers,
        large_repository,
    ):
        """Test system under mixed workload (search, graph, file queries)"""
        
        # Ingest repository
        ingest_response = await test_client.post(
            "/api/v1/repositories/ingest",
            json={"repo_id": large_repository["repo_id"]},
            headers=auth_headers
        )
        job_id = ingest_response.json()["job_id"]
        await self._wait_for_job(test_client, job_id, auth_headers, timeout=300)
        
        async def make_search_request():
            return await test_client.post(
                "/api/v1/search",
                json={"query": "test", "repo_id": large_repository["repo_id"]},
                headers=auth_headers
            )
        
        async def make_graph_request():
            return await test_client.get(
                "/api/v1/dependencies",
                params={
                    "file_path": "src/module_0.py",
                    "repo_id": large_repository["repo_id"],
                    "hops": 2
                },
                headers=auth_headers
            )
        
        async def make_file_request():
            return await test_client.get(
                "/api/v1/file",
                params={
                    "file_path": "src/module_0.py",
                    "repo_id": large_repository["repo_id"]
                },
                headers=auth_headers
            )
        
        # Create mixed workload (60% search, 30% graph, 10% file)
        tasks = []
        for i in range(100):
            if i < 60:
                tasks.append(make_search_request())
            elif i < 90:
                tasks.append(make_graph_request())
            else:
                tasks.append(make_file_request())
        
        # Execute mixed workload
        start = time.time()
        responses = await asyncio.gather(*tasks)
        duration = time.time() - start
        
        success_count = sum(1 for r in responses if r.status_code == 200)
        success_rate = success_count / len(tasks)
        throughput = len(tasks) / duration
        
        print(f"\nMixed Workload Performance:")
        print(f"  Total Requests: {len(tasks)}")
        print(f"  Success Rate: {success_rate:.1%}")
        print(f"  Duration: {duration:.1f}s")
        print(f"  Throughput: {throughput:.1f} req/s")
        
        assert success_rate >= 0.95, f"Success rate {success_rate:.1%} below 95%"

    async def _wait_for_job(self, test_client, job_id: str, auth_headers: Dict[str, str], timeout: int = 30):
        """Helper to wait for job completion"""
        for _ in range(timeout):
            response = await test_client.get(
                f"/api/v1/jobs/{job_id}",
                headers=auth_headers
            )
            status = response.json()["status"]
            if status == "completed":
                return
            elif status == "failed":
                pytest.fail(f"Job {job_id} failed")
            await asyncio.sleep(1)
        pytest.fail(f"Job {job_id} did not complete within {timeout} seconds")


# ============================================================================
# Scalability Tests
# ============================================================================


class TestScalability:
    """Test system scalability"""

    async def test_repository_count_scalability(
        self,
        test_client,
        auth_headers,
    ):
        """Test performance with increasing number of repositories"""
        
        repo_counts = [1, 5, 10]
        
        for count in repo_counts:
            # Ingest multiple repositories
            for i in range(count):
                repo = self._generate_test_repository(
                    num_files=50,
                    repo_name=f"scale-test-{i}"
                )
                response = await test_client.post(
                    "/api/v1/repositories/ingest",
                    json={"repo_id": repo["repo_id"]},
                    headers=auth_headers
                )
                job_id = response.json()["job_id"]
                await self._wait_for_job(test_client, job_id, auth_headers, timeout=120)
            
            # Test search performance
            start = time.time()
            response = await test_client.post(
                "/api/v1/search",
                json={"query": "test function", "k": 10},
                headers=auth_headers
            )
            latency = time.time() - start
            
            assert response.status_code == 200
            print(f"\nSearch latency with {count} repos: {latency:.3f}s")
            
            # Latency should scale sub-linearly
            assert latency < 2.0, f"Latency {latency:.3f}s exceeds 2.0s with {count} repos"

    def _generate_test_repository(self, num_files: int, repo_name: str) -> Dict[str, Any]:
        """Generate test repository"""
        files = []
        for i in range(num_files):
            files.append({
                "path": f"src/file_{i}.py",
                "content": f"def function_{i}(): return {i}",
                "language": "python"
            })
        
        return {
            "repo_id": f"test/{repo_name}",
            "owner": "test",
            "name": repo_name,
            "default_branch": "main",
            "files": files
        }

    async def _wait_for_job(self, test_client, job_id: str, auth_headers: Dict[str, str], timeout: int = 30):
        """Helper to wait for job completion"""
        for _ in range(timeout):
            response = await test_client.get(
                f"/api/v1/jobs/{job_id}",
                headers=auth_headers
            )
            status = response.json()["status"]
            if status == "completed":
                return
            elif status == "failed":
                pytest.fail(f"Job {job_id} failed")
            await asyncio.sleep(1)
        pytest.fail(f"Job {job_id} did not complete within {timeout} seconds")


# Made with Bob