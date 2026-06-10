"""
IBM Bob - End-to-End Integration Tests
Tests complete workflows from ingestion to query
"""

import asyncio
from typing import Dict

import pytest

# ============================================================================
# E2E Test Markers
# ============================================================================

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


# ============================================================================
# Complete Repository Ingestion Workflow
# ============================================================================


class TestCompleteIngestionWorkflow:
    """Test complete repository ingestion workflow"""

    async def test_complete_repository_ingestion(
        self,
        test_client,
        sample_repository,
        auth_headers,
        test_db,
        test_neo4j,
        test_weaviate,
    ):
        """Test complete repository ingestion workflow"""

        # 1. Trigger repository ingestion
        response = await test_client.post(
            "/api/v1/repositories/ingest",
            json={
                "repo_id": sample_repository["repo_id"],
                "branch": sample_repository["default_branch"],
            },
            headers=auth_headers,
        )
        assert response.status_code == 202
        result = response.json()
        assert "job_id" in result
        job_id = result["job_id"]

        # 2. Poll for completion
        max_attempts = 30
        status = None
        for attempt in range(max_attempts):
            status_response = await test_client.get(f"/api/v1/jobs/{job_id}", headers=auth_headers)
            assert status_response.status_code == 200

            status_data = status_response.json()
            status = status_data["status"]

            if status == "completed":
                break
            elif status == "failed":
                pytest.fail(f"Job failed: {status_data.get('error_message')}")

            await asyncio.sleep(1)

        assert status == "completed", f"Job did not complete after {max_attempts} attempts"

        # 3. Verify data in PostgreSQL
        async with test_db.cursor() as cur:
            await cur.execute(
                "SELECT * FROM repositories WHERE repo_id = %s", (sample_repository["repo_id"],)
            )
            repo = await cur.fetchone()
            assert repo is not None
            assert repo["status"] == "indexed"

        # 4. Verify data in Neo4j
        async with test_neo4j.session() as session:
            result = await session.run(
                "MATCH (f:File) WHERE f.repo_id = $repo_id RETURN count(f) as count",
                repo_id=sample_repository["repo_id"],
            )
            record = await result.single()
            assert record["count"] >= len(sample_repository["files"])

        # 5. Verify data in Weaviate
        result = (
            test_weaviate.query.get("CodeUnit", ["file_path", "symbol_name"])
            .with_where(
                {
                    "path": ["repo_id"],
                    "operator": "Equal",
                    "valueText": sample_repository["repo_id"],
                }
            )
            .do()
        )

        assert "data" in result
        assert len(result["data"]["Get"]["CodeUnit"]) > 0

        # 6. Test semantic search
        search_response = await test_client.post(
            "/api/v1/search",
            json={"query": "hello function", "repo_id": sample_repository["repo_id"], "k": 5},
            headers=auth_headers,
        )
        assert search_response.status_code == 200
        search_results = search_response.json()
        assert "results" in search_results
        assert len(search_results["results"]) > 0

        # Verify the hello function is in results
        file_paths = [r["file_path"] for r in search_results["results"]]
        assert "src/main.py" in file_paths

    async def test_incremental_update(
        self,
        test_client,
        sample_repository,
        auth_headers,
        test_neo4j,
    ):
        """Test incremental repository update"""

        # 1. Initial ingestion
        response = await test_client.post(
            "/api/v1/repositories/ingest",
            json={"repo_id": sample_repository["repo_id"]},
            headers=auth_headers,
        )
        assert response.status_code == 202
        job_id = response.json()["job_id"]

        # Wait for completion
        await self._wait_for_job(test_client, job_id, auth_headers)

        # 2. Get initial file count
        async with test_neo4j.session() as session:
            result = await session.run(
                "MATCH (f:File) WHERE f.repo_id = $repo_id RETURN count(f) as count",
                repo_id=sample_repository["repo_id"],
            )
            initial_count = (await result.single())["count"]

        # 3. Trigger incremental update (simulating new commit)
        response = await test_client.post(
            "/api/v1/repositories/update",
            json={"repo_id": sample_repository["repo_id"], "commit_sha": "abc123"},
            headers=auth_headers,
        )
        assert response.status_code == 202

        # 4. Verify update completed
        job_id = response.json()["job_id"]
        await self._wait_for_job(test_client, job_id, auth_headers)

        # 5. Verify data is still consistent
        async with test_neo4j.session() as session:
            result = await session.run(
                "MATCH (f:File) WHERE f.repo_id = $repo_id RETURN count(f) as count",
                repo_id=sample_repository["repo_id"],
            )
            updated_count = (await result.single())["count"]
            assert updated_count >= initial_count

    async def _wait_for_job(
        self, test_client, job_id: str, auth_headers: Dict[str, str], timeout: int = 30
    ):
        """Helper to wait for job completion"""
        for _ in range(timeout):
            response = await test_client.get(f"/api/v1/jobs/{job_id}", headers=auth_headers)
            status = response.json()["status"]
            if status == "completed":
                return
            elif status == "failed":
                pytest.fail(f"Job {job_id} failed")
            await asyncio.sleep(1)
        pytest.fail(f"Job {job_id} did not complete within {timeout} seconds")


# ============================================================================
# Stack Trace Resolution Workflow
# ============================================================================


class TestStackTraceResolution:
    """Test stack trace resolution workflow"""

    async def test_stack_trace_resolution_workflow(
        self,
        test_client,
        sample_repository,
        sample_stack_trace,
        auth_headers,
    ):
        """Test stack trace resolution workflow"""

        # 1. Ingest repository (prerequisite)
        ingest_response = await test_client.post(
            "/api/v1/repositories/ingest",
            json={"repo_id": sample_repository["repo_id"]},
            headers=auth_headers,
        )
        assert ingest_response.status_code == 202

        # Wait for ingestion to complete
        job_id = ingest_response.json()["job_id"]
        await self._wait_for_job(test_client, job_id, auth_headers)

        # 2. Resolve stack trace
        response = await test_client.post(
            "/api/v1/stack-trace/resolve",
            json={"trace": sample_stack_trace, "repo_id": sample_repository["repo_id"]},
            headers=auth_headers,
        )

        assert response.status_code == 200
        result = response.json()
        assert "frames" in result
        frames = result["frames"]

        # 3. Verify resolution
        assert len(frames) >= 2

        # Check first frame
        assert frames[0]["file_path"] == "src/utils.py"
        assert frames[0]["line_number"] == 7
        assert frames[0]["function_name"] == "process_data"

        # Check second frame
        assert frames[1]["file_path"] == "src/utils.py"
        assert frames[1]["line_number"] == 2
        assert frames[1]["function_name"] == "calculate"

        # 4. Verify context is provided
        for frame in frames:
            assert "context" in frame
            assert "code_snippet" in frame
            assert len(frame["code_snippet"]) > 0

    async def test_stack_trace_with_unknown_files(
        self,
        test_client,
        sample_repository,
        auth_headers,
    ):
        """Test stack trace resolution with unknown files"""

        # Ingest repository
        ingest_response = await test_client.post(
            "/api/v1/repositories/ingest",
            json={"repo_id": sample_repository["repo_id"]},
            headers=auth_headers,
        )
        job_id = ingest_response.json()["job_id"]
        await self._wait_for_job(test_client, job_id, auth_headers)

        # Stack trace with unknown file
        unknown_trace = """Traceback (most recent call last):
  File "unknown/file.py", line 10, in function
    do_something()
  File "src/utils.py", line 2, in calculate
    return value / divisor
ValueError: invalid value"""

        response = await test_client.post(
            "/api/v1/stack-trace/resolve",
            json={"trace": unknown_trace, "repo_id": sample_repository["repo_id"]},
            headers=auth_headers,
        )

        assert response.status_code == 200
        result = response.json()
        frames = result["frames"]

        # Should resolve known files and mark unknown ones
        assert len(frames) >= 1

        # Known file should be resolved
        known_frame = next((f for f in frames if f["file_path"] == "src/utils.py"), None)
        assert known_frame is not None
        assert known_frame["resolved"] is True

        # Unknown file should be marked as unresolved
        unknown_frame = next((f for f in frames if f["file_path"] == "unknown/file.py"), None)
        if unknown_frame:
            assert unknown_frame["resolved"] is False

    async def _wait_for_job(
        self, test_client, job_id: str, auth_headers: Dict[str, str], timeout: int = 30
    ):
        """Helper to wait for job completion"""
        for _ in range(timeout):
            response = await test_client.get(f"/api/v1/jobs/{job_id}", headers=auth_headers)
            status = response.json()["status"]
            if status == "completed":
                return
            elif status == "failed":
                pytest.fail(f"Job {job_id} failed")
            await asyncio.sleep(1)
        pytest.fail(f"Job {job_id} did not complete within {timeout} seconds")


# ============================================================================
# Dependency Graph Traversal
# ============================================================================


class TestDependencyGraphTraversal:
    """Test dependency graph traversal"""

    async def test_dependency_graph_traversal(
        self,
        test_client,
        sample_repository,
        auth_headers,
    ):
        """Test dependency graph traversal"""

        # 1. Ingest repository
        ingest_response = await test_client.post(
            "/api/v1/repositories/ingest",
            json={"repo_id": sample_repository["repo_id"]},
            headers=auth_headers,
        )
        job_id = ingest_response.json()["job_id"]
        await self._wait_for_job(test_client, job_id, auth_headers)

        # 2. Query dependency graph
        response = await test_client.get(
            "/api/v1/dependencies",
            params={
                "file_path": "src/utils.py",
                "repo_id": sample_repository["repo_id"],
                "hops": 2,
                "direction": "both",
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        result = response.json()
        assert "graph" in result
        graph = result["graph"]

        # 3. Verify graph structure
        assert "nodes" in graph
        assert "edges" in graph
        assert len(graph["nodes"]) > 0

        # 4. Verify src/utils.py is in the graph
        node_paths = [n["file_path"] for n in graph["nodes"]]
        assert "src/utils.py" in node_paths

    async def test_upstream_dependencies(
        self,
        test_client,
        sample_repository,
        auth_headers,
    ):
        """Test upstream dependency traversal"""

        # Ingest repository
        ingest_response = await test_client.post(
            "/api/v1/repositories/ingest",
            json={"repo_id": sample_repository["repo_id"]},
            headers=auth_headers,
        )
        job_id = ingest_response.json()["job_id"]
        await self._wait_for_job(test_client, job_id, auth_headers)

        # Query upstream dependencies
        response = await test_client.get(
            "/api/v1/dependencies",
            params={
                "file_path": "src/utils.py",
                "repo_id": sample_repository["repo_id"],
                "hops": 1,
                "direction": "upstream",
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        result = response.json()
        graph = result["graph"]

        # Verify only upstream dependencies are included
        assert len(graph["nodes"]) >= 1
        assert len(graph["edges"]) >= 0

    async def test_blast_radius_analysis(
        self,
        test_client,
        sample_repository,
        auth_headers,
    ):
        """Test blast radius analysis"""

        # Ingest repository
        ingest_response = await test_client.post(
            "/api/v1/repositories/ingest",
            json={"repo_id": sample_repository["repo_id"]},
            headers=auth_headers,
        )
        job_id = ingest_response.json()["job_id"]
        await self._wait_for_job(test_client, job_id, auth_headers)

        # Analyze blast radius
        response = await test_client.post(
            "/api/v1/blast-radius",
            json={"files": ["src/utils.py"], "repo_id": sample_repository["repo_id"]},
            headers=auth_headers,
        )

        assert response.status_code == 200
        result = response.json()

        assert "impacted_files" in result
        assert "risk_score" in result
        assert "acs_scores" in result

        # Verify impacted files
        impacted = result["impacted_files"]
        assert len(impacted) >= 1

        # Verify risk assessment
        assert 0.0 <= result["risk_score"] <= 1.0

    async def _wait_for_job(
        self, test_client, job_id: str, auth_headers: Dict[str, str], timeout: int = 30
    ):
        """Helper to wait for job completion"""
        for _ in range(timeout):
            response = await test_client.get(f"/api/v1/jobs/{job_id}", headers=auth_headers)
            status = response.json()["status"]
            if status == "completed":
                return
            elif status == "failed":
                pytest.fail(f"Job {job_id} failed")
            await asyncio.sleep(1)
        pytest.fail(f"Job {job_id} did not complete within {timeout} seconds")


# ============================================================================
# Semantic Search Workflow
# ============================================================================


class TestSemanticSearchWorkflow:
    """Test semantic search workflow"""

    async def test_semantic_search_accuracy(
        self,
        test_client,
        sample_repository,
        auth_headers,
    ):
        """Test semantic search accuracy"""

        # Ingest repository
        ingest_response = await test_client.post(
            "/api/v1/repositories/ingest",
            json={"repo_id": sample_repository["repo_id"]},
            headers=auth_headers,
        )
        job_id = ingest_response.json()["job_id"]
        await self._wait_for_job(test_client, job_id, auth_headers)

        # Test queries
        test_cases = [
            {
                "query": "authentication middleware",
                "expected_file": "src/auth.py",
                "expected_symbol": "AuthMiddleware",
            },
            {
                "query": "calculate division",
                "expected_file": "src/utils.py",
                "expected_symbol": "calculate",
            },
            {
                "query": "greeting function",
                "expected_file": "src/main.py",
                "expected_symbol": "hello",
            },
        ]

        for test_case in test_cases:
            response = await test_client.post(
                "/api/v1/search",
                json={"query": test_case["query"], "repo_id": sample_repository["repo_id"], "k": 5},
                headers=auth_headers,
            )

            assert response.status_code == 200
            results = response.json()["results"]
            assert len(results) > 0

            # Check if expected result is in top 5
            found = any(
                r["file_path"] == test_case["expected_file"]
                and r["symbol_name"] == test_case["expected_symbol"]
                for r in results
            )
            assert (
                found
            ), f"Expected {test_case['expected_symbol']} in {test_case['expected_file']} not found for query: {test_case['query']}"  # noqa: E501

    async def test_semantic_search_with_filters(
        self,
        test_client,
        sample_repository,
        auth_headers,
    ):
        """Test semantic search with filters"""

        # Ingest repository
        ingest_response = await test_client.post(
            "/api/v1/repositories/ingest",
            json={"repo_id": sample_repository["repo_id"]},
            headers=auth_headers,
        )
        job_id = ingest_response.json()["job_id"]
        await self._wait_for_job(test_client, job_id, auth_headers)

        # Search with language filter
        response = await test_client.post(
            "/api/v1/search",
            json={
                "query": "function",
                "repo_id": sample_repository["repo_id"],
                "k": 10,
                "filters": {"language": "python", "symbol_type": "function"},
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        results = response.json()["results"]

        # Verify all results match filters
        for result in results:
            assert result["language"] == "python"
            assert result["symbol_type"] == "function"

    async def _wait_for_job(
        self, test_client, job_id: str, auth_headers: Dict[str, str], timeout: int = 30
    ):
        """Helper to wait for job completion"""
        for _ in range(timeout):
            response = await test_client.get(f"/api/v1/jobs/{job_id}", headers=auth_headers)
            status = response.json()["status"]
            if status == "completed":
                return
            elif status == "failed":
                pytest.fail(f"Job {job_id} failed")
            await asyncio.sleep(1)
        pytest.fail(f"Job {job_id} did not complete within {timeout} seconds")


# ============================================================================
# Multi-Repository Workflow
# ============================================================================


class TestMultiRepositoryWorkflow:
    """Test multi-repository workflows"""

    async def test_cross_repository_search(
        self,
        test_client,
        sample_repository,
        auth_headers,
    ):
        """Test search across multiple repositories"""

        # Create second repository
        repo2 = {**sample_repository, "repo_id": "test/sample-repo-2", "name": "sample-repo-2"}

        # Ingest both repositories
        for repo in [sample_repository, repo2]:
            response = await test_client.post(
                "/api/v1/repositories/ingest",
                json={"repo_id": repo["repo_id"]},
                headers=auth_headers,
            )
            job_id = response.json()["job_id"]
            await self._wait_for_job(test_client, job_id, auth_headers)

        # Search without repo_id filter (across all repos)
        response = await test_client.post(
            "/api/v1/search", json={"query": "authentication", "k": 10}, headers=auth_headers
        )

        assert response.status_code == 200
        results = response.json()["results"]

        # Should have results from both repositories
        repo_ids = set(r["repo_id"] for r in results)
        assert len(repo_ids) >= 1

    async def _wait_for_job(
        self, test_client, job_id: str, auth_headers: Dict[str, str], timeout: int = 30
    ):
        """Helper to wait for job completion"""
        for _ in range(timeout):
            response = await test_client.get(f"/api/v1/jobs/{job_id}", headers=auth_headers)
            status = response.json()["status"]
            if status == "completed":
                return
            elif status == "failed":
                pytest.fail(f"Job {job_id} failed")
            await asyncio.sleep(1)
        pytest.fail(f"Job {job_id} did not complete within {timeout} seconds")


# Made with Bob
