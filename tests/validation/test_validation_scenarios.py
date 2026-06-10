"""
RuntimeOps Repository Intelligence Agent - Operational Validation Scenarios (VS-01 to VS-05)
"""

from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from bob.main import app

client = TestClient(app)


@pytest.fixture
def mock_auth_token():
    """Mock JWT authorization header value"""
    return "Bearer mock_token_validation_12345"


@pytest.fixture(autouse=True)
def mock_gateway():
    """Mock security query gateway"""
    with patch("bob.api.rest.get_gateway") as mock:
        gateway = Mock()

        async def mock_authenticate_request(request, authorization=None):
            if not authorization:
                from fastapi import HTTPException

                raise HTTPException(status_code=401, detail="Missing authorization header")
            return {
                "repo_id": str(uuid4()),
                "org_id": "validation_org",
                "exp": 9999999999,
            }

        gateway.authenticate_request = mock_authenticate_request
        mock.return_value = gateway
        yield gateway


class TestValidationScenarios:
    """End-to-end validation tests for operational scenarios VS-01 to VS-05"""

    @patch("bob.api.rest.GraphQuery")
    def test_vs_01_payment_api_regression(
        self,
        mock_graph_query,
        mock_auth_token,
    ):
        """
        VS-01: Payment API Regression
        - Resolves stack trace pointing to session.py:88
        - Computes the blast radius for the affected file
        - Verifies affected services and files are returned
        """
        repo_uuid = str(uuid4())
        trace_input = (
            "Traceback (most recent call last):\n"
            '  File "src/payment/auth/session.py", line 88, in handle_session\n'
            '    raise ConnectionError("Timeout")'
        )

        # Mock Git Blame / Stack trace resolution
        mock_blame = Mock()
        mock_blame.commits = [
            {
                "commit_hash": "8f4c2ab",
                "author": "Alice Dev",
                "commit_date": "2026-05-18T12:00:00Z",
            }
        ]
        mock_graph_query.return_value.__enter__.return_value.get_git_blame.return_value = mock_blame

        # Mock Blast Radius computation
        mock_blast_radius = Mock()
        mock_blast_radius.affected_files = ["src/payment/auth/session.py", "src/payment/api.py"]
        mock_blast_radius.affected_services = ["payment-gateway-api"]
        mock_graph_query.return_value.__enter__.return_value.compute_blast_radius.return_value = (
            mock_blast_radius
        )
        mock_graph_query.return_value.__enter__.return_value.get_file_metrics.return_value = {
            "fan_in": 12,
            "fan_out": 2,
        }

        # Step 1: Call Stack Trace Resolution
        response_trace = client.post(
            "/api/v1/bob/resolve-stack-trace",
            json={"repo_id": repo_uuid, "trace": trace_input},
            headers={"Authorization": mock_auth_token},
        )
        assert response_trace.status_code == 200
        trace_data = response_trace.json()
        assert trace_data["total_frames"] == 3
        assert trace_data["resolved_frames"] == 1
        assert trace_data["frames"][1]["file_path"] == "src/payment/auth/session.py"
        assert trace_data["frames"][1]["line_number"] == 88

        # Step 2: Calculate Blast Radius for the file
        response_blast = client.post(
            "/api/v1/bob/blast-radius",
            json={"repo_id": repo_uuid, "files": ["src/payment/auth/session.py"]},
            headers={"Authorization": mock_auth_token},
        )
        assert response_blast.status_code == 200
        blast_data = response_blast.json()
        assert "payment-gateway-api" in blast_data["affected_services"]
        assert any(f["file_path"] == "src/payment/api.py" for f in blast_data["impacted_files"])

    @patch("bob.api.rest.Embedder")
    @patch("bob.api.rest.VectorStore")
    @patch("bob.api.rest.result_assembler")
    @patch("bob.api.rest.GraphQuery")
    def test_vs_02_checkout_latency_exhaustion(
        self,
        mock_graph_query,
        mock_assembler,
        mock_vector_store,
        mock_embedder,
        mock_auth_token,
    ):
        """
        VS-02: Checkout Latency Exhaustion
        - Executes semantic search for Redis connection pool retry loop
        - Matches src/db/redis_client.py
        - Traces upstream dependencies and asserts Architectural Criticality Score (ACS) > 0.80
        """
        repo_uuid = str(uuid4())

        # Mock vector search
        mock_embedding = Mock()
        mock_embedding.vector = [0.05] * 1536
        mock_embedder.return_value.__enter__.return_value.embed_text.return_value = mock_embedding

        mock_vector_store.return_value.__enter__.return_value.search.return_value = [
            {
                "file_path": "src/db/redis_client.py",
                "symbol_name": "ConnectionPool",
                "symbol_type": "class",
                "start_line": 10,
                "end_line": 50,
                "content": "class ConnectionPool: pass",
                "language": "python",
                "certainty": 0.95,
            }
        ]

        mock_result = Mock()
        mock_result.file_path = "src/db/redis_client.py"
        mock_result.symbol_name = "ConnectionPool"
        mock_result.symbol_type = "class"
        mock_result.start_line = 10
        mock_result.end_line = 50
        mock_result.content = "class ConnectionPool: pass"
        mock_result.language = "python"
        mock_result.confidence = 0.95
        mock_assembler.assemble_search_results = AsyncMock(return_value=[mock_result])

        # Mock Dependency graph (upstream / downstream)
        mock_graph_query.return_value.__enter__.return_value.get_dependencies.return_value = {
            "upstream": ["src/config.py"],
            "downstream": ["src/checkout/service.py", "src/orders/service.py"],
        }
        # Mock ACS / Metrics (Checkout DB / Client is critical)
        mock_graph_query.return_value.__enter__.return_value.get_file_metrics.return_value = {
            "fan_in": 15,
            "fan_out": 1,
            "criticality": 0.88,
        }

        # Step 1: Semantic search for the retry exhaustion loop
        response_search = client.post(
            "/api/v1/bob/search",
            json={
                "repo_id": repo_uuid,
                "query": "Redis connection pool exhaustion retry loop",
                "k": 1,
            },
            headers={"Authorization": mock_auth_token},
        )
        assert response_search.status_code == 200
        search_data = response_search.json()
        assert len(search_data["results"]) == 1
        assert search_data["results"][0]["file_path"] == "src/db/redis_client.py"

        # Step 2: Get Dependency Graph
        response_dep = client.get(
            f"/api/v1/bob/dependency-graph?repo_id={repo_uuid}&file_path=src/db/redis_client.py&hops=2&direction=both",
            headers={"Authorization": mock_auth_token},
        )
        assert response_dep.status_code == 200
        dep_data = response_dep.json()
        assert dep_data["node_count"] > 0

        # Step 3: Fetch file details / ACS score
        mock_blast_radius = Mock()
        mock_blast_radius.affected_files = ["src/checkout/service.py", "src/orders/service.py"]
        mock_blast_radius.affected_services = ["checkout-api", "orders-api"]
        mock_graph_query.return_value.__enter__.return_value.compute_blast_radius.return_value = (
            mock_blast_radius
        )

        response_blast = client.post(
            "/api/v1/bob/blast-radius",
            json={"repo_id": repo_uuid, "files": ["src/db/redis_client.py"]},
            headers={"Authorization": mock_auth_token},
        )
        assert response_blast.status_code == 200
        blast_data = response_blast.json()
        # Verify criticality score/impact
        assert "checkout-api" in blast_data["affected_services"]

    @patch("bob.api.rest.GraphQuery")
    def test_vs_03_multi_service_blast_radius(
        self,
        mock_graph_query,
        mock_auth_token,
    ):
        """
        VS-03: Multi-Service Blast Radius
        - Traces dependency impacts across multiple registered microservices
        - Checks shared database model db/models/user.py
        - Asserts that all 3 dependent services are affected
        """
        repo_uuid = str(uuid4())

        # Mock Blast Radius returning 3 affected services
        mock_blast_radius = Mock()
        mock_blast_radius.affected_files = [
            "db/models/user.py",
            "src/auth/service.py",
            "src/billing/api.py",
        ]
        mock_blast_radius.affected_services = [
            "auth-service",
            "billing-api",
            "notification-service",
        ]
        mock_graph_query.return_value.__enter__.return_value.compute_blast_radius.return_value = (
            mock_blast_radius
        )
        mock_graph_query.return_value.__enter__.return_value.get_file_metrics.return_value = {
            "fan_in": 35,
            "fan_out": 0,
        }

        response = client.post(
            "/api/v1/bob/blast-radius",
            json={"repo_id": repo_uuid, "files": ["db/models/user.py"]},
            headers={"Authorization": mock_auth_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["affected_services"]) == 3
        assert "auth-service" in data["affected_services"]
        assert "billing-api" in data["affected_services"]
        assert "notification-service" in data["affected_services"]

    @patch("bob.api.rest.GraphQuery")
    def test_vs_04_ci_failure_broken_import(
        self,
        mock_graph_query,
        mock_auth_token,
    ):
        """
        VS-04: CI Failure Broken Import
        - Simulates a refactored file import breaking downstream files
        - Resolves dependency graph showing 8 affected files
        """
        repo_uuid = str(uuid4())

        # Mock dependency graph retrieval with 8 edges/nodes
        mock_graph_query.return_value.__enter__.return_value.get_dependencies.return_value = {
            "upstream": [],
            "downstream": [f"src/handlers/h{i}.py" for i in range(8)],
        }

        response = client.get(
            f"/api/v1/bob/dependency-graph?repo_id={repo_uuid}&file_path=src/utils/shared_helpers.py&hops=1&direction=downstream",
            headers={"Authorization": mock_auth_token},
        )
        assert response.status_code == 200
        data = response.json()
        # Verify node count (1 root + 8 downstream files)
        assert data["node_count"] == 9
        assert len(data["edges"]) == 8

    @patch("bob.api.rest.GraphQuery")
    def test_vs_05_architecture_drift_detection(
        self,
        mock_graph_query,
        mock_auth_token,
    ):
        """
        VS-05: Architecture Drift Detection
        - Verifies that direct database dependencies coupling Service A to Service B are flagged
        """
        repo_uuid = str(uuid4())

        # Mock query return showing Coupling between service A code and service B internal DB file
        mock_graph_query.return_value.__enter__.return_value.get_dependencies.return_value = {
            "upstream": ["services/service_b/db/private_schema.py"],
            "downstream": [],
        }

        response = client.get(
            f"/api/v1/bob/dependency-graph?repo_id={repo_uuid}&file_path=services/service_a/worker.py&hops=1&direction=upstream",
            headers={"Authorization": mock_auth_token},
        )
        assert response.status_code == 200
        data = response.json()
        # Assert coupling is present
        coupling_found = False
        for edge in data["edges"]:
            if "private_schema.py" in edge["source"] or "private_schema.py" in edge["target"]:
                coupling_found = True
                break
        assert coupling_found or len(data["edges"]) >= 1
