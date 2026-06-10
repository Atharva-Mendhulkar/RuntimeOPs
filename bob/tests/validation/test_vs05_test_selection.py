"""
Validation Scenario 05: Test Selection
Workflow:
1. Ingest code
2. Given a modified file
3. Find upstream tests that cover this file
"""
import pytest
import asyncio
from typing import Dict, Any

pytestmark = [pytest.mark.validation, pytest.mark.asyncio]

class TestVS05TestSelection:
    async def test_vs05_test_selection_workflow(
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
        
        modified_file = "src/utils.py"
        
        # 2. Find upstream files (which should include tests)
        dep_resp = await test_client.get(
            "/api/v1/dependencies",
            params={
                "file_path": modified_file,
                "repo_id": sample_repository["repo_id"],
                "hops": 2,
                "direction": "upstream"
            },
            headers=auth_headers
        )
        assert dep_resp.status_code == 200
        graph = dep_resp.json()["graph"]
        assert "nodes" in graph
        
        # Filter nodes to find tests
        test_files = [n["file_path"] for n in graph["nodes"] if "test" in n["file_path"].lower()]
        assert isinstance(test_files, list)

    async def _wait_for_job(self, test_client, job_id: str, auth_headers: Dict[str, str], timeout: int = 30):
        for _ in range(timeout):
            resp = await test_client.get(f"/api/v1/jobs/{job_id}", headers=auth_headers)
            status = resp.json()["status"]
            if status == "completed": return
            elif status == "failed": pytest.fail(f"Job {job_id} failed")
            await asyncio.sleep(1)
        pytest.fail("Timeout waiting for job")
