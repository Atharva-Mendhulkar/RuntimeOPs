"""
Validation Scenario 04: Architecture Mapping
Workflow:
1. Ingest code
2. Query large subgraph starting from entrypoint
3. Assess architecture boundaries
"""
import pytest
import asyncio
from typing import Dict, Any

pytestmark = [pytest.mark.validation, pytest.mark.asyncio]

class TestVS04ArchitectureMapping:
    async def test_vs04_architecture_mapping_workflow(
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
        
        entrypoint = "src/main.py"
        
        # 2. Query architecture boundaries (large hop count)
        dep_resp = await test_client.get(
            "/api/v1/dependencies",
            params={
                "file_path": entrypoint,
                "repo_id": sample_repository["repo_id"],
                "hops": 5,
                "direction": "both"
            },
            headers=auth_headers
        )
        assert dep_resp.status_code == 200
        graph = dep_resp.json()["graph"]
        assert "nodes" in graph
        assert len(graph["nodes"]) > 0

    async def _wait_for_job(self, test_client, job_id: str, auth_headers: Dict[str, str], timeout: int = 30):
        for _ in range(timeout):
            resp = await test_client.get(f"/api/v1/jobs/{job_id}", headers=auth_headers)
            status = resp.json()["status"]
            if status == "completed": return
            elif status == "failed": pytest.fail(f"Job {job_id} failed")
            await asyncio.sleep(1)
        pytest.fail("Timeout waiting for job")
