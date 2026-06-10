"""
Validation Scenario 03: Code Discovery
Workflow:
1. Ingest code
2. Semantic search based on natural language
3. Graph traversal from search results to find usages
"""
import pytest
import asyncio
from typing import Dict, Any

pytestmark = [pytest.mark.validation, pytest.mark.asyncio]

class TestVS03CodeDiscovery:
    async def test_vs03_code_discovery_workflow(
        self,
        test_client,
        sample_repository,
        auth_headers,
    ):
        # 1. Ingest repo
        ingest_resp = await test_client.post(
            "/api/v1/repositories/ingest",
            json={"repo_id": sample_repository["repo_id"]},
            headers=auth_headers
        )
        assert ingest_resp.status_code == 202
        await self._wait_for_job(test_client, ingest_resp.json()["job_id"], auth_headers)
        
        # 2. Semantic search
        search_resp = await test_client.post(
            "/api/v1/search",
            json={"query": "calculate division", "repo_id": sample_repository["repo_id"], "k": 1},
            headers=auth_headers
        )
        assert search_resp.status_code == 200
        results = search_resp.json()["results"]
        assert len(results) > 0
        discovered_file = results[0]["file_path"]
        
        # 3. Find usages (downstream)
        dep_resp = await test_client.get(
            "/api/v1/dependencies",
            params={
                "file_path": discovered_file,
                "repo_id": sample_repository["repo_id"],
                "hops": 1,
                "direction": "downstream"
            },
            headers=auth_headers
        )
        assert dep_resp.status_code == 200
        assert "graph" in dep_resp.json()

    async def _wait_for_job(self, test_client, job_id: str, auth_headers: Dict[str, str], timeout: int = 30):
        for _ in range(timeout):
            resp = await test_client.get(f"/api/v1/jobs/{job_id}", headers=auth_headers)
            status = resp.json()["status"]
            if status == "completed": return
            elif status == "failed": pytest.fail(f"Job {job_id} failed")
            await asyncio.sleep(1)
        pytest.fail("Timeout waiting for job")
