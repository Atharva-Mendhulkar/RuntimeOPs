"""
Validation Scenario 01: Incident Response
Workflow:
1. Ingest code
2. Resolve stack trace to files/functions
3. Determine blast radius of failing component
4. Search for related context
"""
import pytest
import asyncio
from typing import Dict, Any

pytestmark = [pytest.mark.validation, pytest.mark.asyncio]

class TestVS01IncidentResponse:
    async def test_vs01_incident_response_workflow(
        self,
        test_client,
        sample_repository,
        sample_stack_trace,
        auth_headers,
    ):
        # 1. Ingest repo
        ingest_resp = await test_client.post(
            "/api/v1/repositories/ingest",
            json={"repo_id": sample_repository["repo_id"]},
            headers=auth_headers
        )
        assert ingest_resp.status_code == 202
        job_id = ingest_resp.json()["job_id"]
        await self._wait_for_job(test_client, job_id, auth_headers)
        
        # 2. Resolve Stack Trace
        trace_resp = await test_client.post(
            "/api/v1/stack-trace/resolve",
            json={"trace": sample_stack_trace, "repo_id": sample_repository["repo_id"]},
            headers=auth_headers
        )
        assert trace_resp.status_code == 200
        frames = trace_resp.json()["frames"]
        assert len(frames) > 0
        
        failing_file = frames[0]["file_path"]
        
        # 3. Analyze Blast Radius
        blast_resp = await test_client.post(
            "/api/v1/blast-radius",
            json={"files": [failing_file], "repo_id": sample_repository["repo_id"]},
            headers=auth_headers
        )
        assert blast_resp.status_code == 200
        blast_data = blast_resp.json()
        assert "impacted_files" in blast_data
        
        # 4. Semantic Search
        search_resp = await test_client.post(
            "/api/v1/search",
            json={"query": "error handling", "repo_id": sample_repository["repo_id"], "k": 3},
            headers=auth_headers
        )
        assert search_resp.status_code == 200
        assert len(search_resp.json()["results"]) > 0

    async def _wait_for_job(self, test_client, job_id: str, auth_headers: Dict[str, str], timeout: int = 30):
        for _ in range(timeout):
            resp = await test_client.get(f"/api/v1/jobs/{job_id}", headers=auth_headers)
            status = resp.json()["status"]
            if status == "completed": return
            elif status == "failed": pytest.fail(f"Job {job_id} failed")
            await asyncio.sleep(1)
        pytest.fail("Timeout waiting for job")
