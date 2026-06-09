"""
IBM Bob - Integration Tests for API Endpoints
Tests for all 8 REST endpoints with mocked backends
"""

import pytest
from uuid import uuid4
from unittest.mock import Mock, patch, MagicMock, AsyncMock

from fastapi.testclient import TestClient

from bob.main import app
from bob.api.models import (
    SearchRequest,
    StackTraceRequest,
    BlastRadiusRequest,
    BatchRequest,
    SubQuery,
)


# Create test client
client = TestClient(app)


# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def mock_auth_token():
    """Mock JWT token for authentication"""
    return "Bearer mock_token_12345"


@pytest.fixture
def mock_repo_id():
    """Mock repository UUID"""
    return str(uuid4())


@pytest.fixture(autouse=True)
def mock_gateway():
    """Mock query gateway"""
    with patch("bob.api.rest.get_gateway") as mock:
        gateway = Mock()
        
        async def mock_authenticate_request(request, authorization=None):
            if not authorization:
                from fastapi import HTTPException
                raise HTTPException(status_code=401, detail="Missing authorization header")
            return {
                "repo_id": str(uuid4()),
                "org_id": "test_org",
                "exp": 9999999999,
            }
            
        gateway.authenticate_request = mock_authenticate_request
        mock.return_value = gateway
        yield gateway


# ============================================================================
# EP-001: Search Endpoint Tests
# ============================================================================


class TestSearchEndpoint:
    """Test /api/v1/bob/search endpoint"""

    @patch("bob.api.rest.Embedder")
    @patch("bob.api.rest.VectorStore")
    @patch("bob.api.rest.result_assembler")
    def test_search_success(
        self,
        mock_assembler,
        mock_vector_store,
        mock_embedder,
        mock_gateway,
        mock_auth_token,
        mock_repo_id,
    ):
        """Test successful search"""
        # Mock embedder
        mock_embedding = Mock()
        mock_embedding.vector = [0.1] * 1536
        mock_embedder.return_value.__enter__.return_value.embed_text.return_value = mock_embedding

        # Mock vector store
        mock_vector_store.return_value.__enter__.return_value.search.return_value = [
            {
                "file_path": "src/auth.py",
                "symbol_name": "authenticate",
                "symbol_type": "function",
                "start_line": 10,
                "end_line": 20,
                "content": "def authenticate(): pass",
                "language": "python",
                "certainty": 0.9,
            }
        ]

        # Mock assembler
        mock_result = Mock()
        mock_result.file_path = "src/auth.py"
        mock_result.symbol_name = "authenticate"
        mock_result.symbol_type = "function"
        mock_result.start_line = 10
        mock_result.end_line = 20
        mock_result.content = "def authenticate(): pass"
        mock_result.language = "python"
        mock_result.confidence = 0.9
        
        mock_assembler.assemble_search_results = AsyncMock(return_value=[mock_result])

        # Make request
        response = client.post(
            "/api/v1/bob/search",
            json={
                "repo_id": mock_repo_id,
                "query": "authentication function",
                "k": 10,
            },
            headers={"Authorization": mock_auth_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert "total" in data
        assert "query_time_ms" in data

    def test_search_invalid_request(self, mock_gateway, mock_auth_token):
        """Test search with invalid request"""
        response = client.post(
            "/api/v1/bob/search",
            json={
                "repo_id": "invalid-uuid",
                "query": "test",
                "k": 10,
            },
            headers={"Authorization": mock_auth_token},
        )

        assert response.status_code == 422  # Validation error

    def test_search_unauthorized(self):
        """Test search without authentication"""
        response = client.post(
            "/api/v1/bob/search",
            json={
                "repo_id": str(uuid4()),
                "query": "test query",
                "k": 10,
            },
        )

        assert response.status_code == 401


# ============================================================================
# EP-002: Stack Trace Resolution Tests
# ============================================================================


class TestStackTraceEndpoint:
    """Test /api/v1/bob/resolve-stack-trace endpoint"""

    @patch("bob.api.rest.GraphQuery")
    def test_resolve_stack_trace_success(
        self,
        mock_graph_query,
        mock_gateway,
        mock_auth_token,
        mock_repo_id,
    ):
        """Test successful stack trace resolution"""
        # Mock graph query
        mock_blame = Mock()
        mock_blame.commits = [
            {
                "commit_hash": "abc123",
                "author": "John Doe",
                "commit_date": "2024-01-01T00:00:00Z",
            }
        ]
        mock_graph_query.return_value.__enter__.return_value.get_git_blame.return_value = mock_blame

        # Make request
        response = client.post(
            "/api/v1/bob/resolve-stack-trace",
            json={
                "repo_id": mock_repo_id,
                "trace": 'File "app.py", line 42, in handler\n    process_request()',
            },
            headers={"Authorization": mock_auth_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert "frames" in data
        assert "total_frames" in data
        assert "resolved_frames" in data


# ============================================================================
# EP-003: Dependency Graph Tests
# ============================================================================


class TestDependencyGraphEndpoint:
    """Test /api/v1/bob/dependency-graph endpoint"""

    @patch("bob.api.rest.GraphQuery")
    def test_get_dependency_graph_success(
        self,
        mock_graph_query,
        mock_gateway,
        mock_auth_token,
        mock_repo_id,
    ):
        """Test successful dependency graph retrieval"""
        # Mock graph query
        mock_graph_query.return_value.__enter__.return_value.get_dependencies.return_value = {
            "upstream": ["src/utils.py", "src/config.py"],
            "downstream": ["src/handler.py"],
        }

        # Make request
        response = client.get(
            f"/api/v1/bob/dependency-graph?repo_id={mock_repo_id}&file_path=src/app.py&hops=3&direction=both",
            headers={"Authorization": mock_auth_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert "root_file" in data
        assert "edges" in data
        assert "node_count" in data
        assert "edge_count" in data

    def test_get_dependency_graph_invalid_hops(
        self,
        mock_gateway,
        mock_auth_token,
        mock_repo_id,
    ):
        """Test dependency graph with invalid hops"""
        response = client.get(
            f"/api/v1/bob/dependency-graph?repo_id={mock_repo_id}&file_path=src/app.py&hops=20",
            headers={"Authorization": mock_auth_token},
        )

        assert response.status_code == 400


# ============================================================================
# EP-004: Blast Radius Tests
# ============================================================================


class TestBlastRadiusEndpoint:
    """Test /api/v1/bob/blast-radius endpoint"""

    @patch("bob.api.rest.GraphQuery")
    def test_compute_blast_radius_success(
        self,
        mock_graph_query,
        mock_gateway,
        mock_auth_token,
        mock_repo_id,
    ):
        """Test successful blast radius computation"""
        # Mock blast radius result
        mock_blast_radius = Mock()
        mock_blast_radius.affected_files = ["src/handler.py", "src/service.py"]
        mock_blast_radius.affected_services = ["api-service"]
        
        mock_graph_query.return_value.__enter__.return_value.compute_blast_radius.return_value = mock_blast_radius
        mock_graph_query.return_value.__enter__.return_value.get_file_metrics.return_value = {
            "fan_in": 5,
            "fan_out": 3,
        }

        # Make request
        response = client.post(
            "/api/v1/bob/blast-radius",
            json={
                "repo_id": mock_repo_id,
                "files": ["src/auth.py"],
            },
            headers={"Authorization": mock_auth_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert "changed_files" in data
        assert "impacted_files" in data
        assert "total_impacted" in data
        assert "affected_services" in data


# ============================================================================
# EP-005: File Retrieval Tests
# ============================================================================


class TestFileEndpoint:
    """Test /api/v1/bob/file endpoint"""

    @patch("bob.api.rest.FileCache")
    def test_get_file_from_cache(
        self,
        mock_cache,
        mock_gateway,
        mock_auth_token,
        mock_repo_id,
    ):
        """Test file retrieval from cache"""
        # Mock cache hit
        mock_cache.return_value.__enter__.return_value.get.return_value = "def main(): pass"

        # Make request
        response = client.get(
            f"/api/v1/bob/file?repo_id={mock_repo_id}&file_path=src/app.py",
            headers={"Authorization": mock_auth_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert "file_path" in data
        assert "content" in data
        assert "language" in data

    @patch("bob.api.rest.FileCache")
    def test_get_file_not_found(
        self,
        mock_cache,
        mock_gateway,
        mock_auth_token,
        mock_repo_id,
    ):
        """Test file not found"""
        # Mock cache miss
        mock_cache.return_value.__enter__.return_value.get.return_value = None

        # Make request
        response = client.get(
            f"/api/v1/bob/file?repo_id={mock_repo_id}&file_path=nonexistent.py",
            headers={"Authorization": mock_auth_token},
        )

        assert response.status_code == 404


# ============================================================================
# EP-006: Commit Diff Tests
# ============================================================================


class TestCommitDiffEndpoint:
    """Test /api/v1/bob/commit-diff endpoint"""

    def test_analyze_commit_diff(
        self,
        mock_gateway,
        mock_auth_token,
        mock_repo_id,
    ):
        """Test commit diff analysis"""
        # Make request
        response = client.get(
            f"/api/v1/bob/commit-diff?repo_id={mock_repo_id}&commit_sha=abc123",
            headers={"Authorization": mock_auth_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert "commit_sha" in data
        assert "changed_files" in data


# ============================================================================
# EP-007: Health Check Tests
# ============================================================================


class TestHealthEndpoint:
    """Test /api/v1/bob/health endpoint"""

    @patch("bob.api.rest.GraphQuery")
    @patch("bob.api.rest.VectorStore")
    @patch("bob.api.rest.IndexRegistryManager")
    @patch("bob.api.rest.FileCache")
    def test_health_check_all_healthy(
        self,
        mock_cache,
        mock_registry,
        mock_vector_store,
        mock_graph_query,
    ):
        """Test health check with all services healthy"""
        # Mock all services as healthy
        mock_graph_query.return_value.__enter__.return_value = Mock()
        mock_vector_store.return_value.__enter__.return_value.get_stats.return_value = {
            "total_embeddings": 1000
        }
        mock_registry.return_value.__enter__.return_value.get_health_metrics.return_value = {
            "total_repositories": 5
        }
        mock_cache.return_value.__enter__.return_value.get_stats.return_value = {
            "hit_rate": 0.85
        }

        # Make request
        response = client.get("/api/v1/bob/health")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "services" in data
        assert "metrics" in data
        assert data["status"] in ("healthy", "degraded", "unhealthy")

    @patch("bob.api.rest.GraphQuery")
    @patch("bob.api.rest.VectorStore")
    @patch("bob.api.rest.IndexRegistryManager")
    @patch("bob.api.rest.FileCache")
    def test_health_check_degraded(
        self,
        mock_cache,
        mock_registry,
        mock_vector_store,
        mock_graph_query,
    ):
        """Test health check with some services unhealthy"""
        # Mock Neo4j as unhealthy
        mock_graph_query.return_value.__enter__.side_effect = Exception("Connection failed")
        
        # Other services healthy
        mock_vector_store.return_value.__enter__.return_value.get_stats.return_value = {}
        mock_registry.return_value.__enter__.return_value.get_health_metrics.return_value = {}
        mock_cache.return_value.__enter__.return_value.get_stats.return_value = {}

        # Make request
        response = client.get("/api/v1/bob/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ("degraded", "unhealthy")
        assert "last_error" in data


# ============================================================================
# EP-008: Batch Query Tests
# ============================================================================


class TestBatchEndpoint:
    """Test /api/v1/bob/batch endpoint"""

    @patch("bob.api.rest.Embedder")
    @patch("bob.api.rest.VectorStore")
    @patch("bob.api.rest.result_assembler")
    @patch("bob.api.rest.GraphQuery")
    def test_batch_query_success(
        self,
        mock_graph_query,
        mock_assembler,
        mock_vector_store,
        mock_embedder,
        mock_gateway,
        mock_auth_token,
        mock_repo_id,
    ):
        """Test successful batch query"""
        # Mock dependencies
        mock_embedding = Mock()
        mock_embedding.vector = [0.1] * 1536
        mock_embedder.return_value.__enter__.return_value.embed_text.return_value = mock_embedding
        
        mock_vector_store.return_value.__enter__.return_value.search.return_value = []
        mock_assembler.assemble_search_results = AsyncMock(return_value=[])
        
        mock_graph_query.return_value.__enter__.return_value.get_dependencies.return_value = {
            "upstream": [],
            "downstream": [],
        }

        # Make request
        response = client.post(
            "/api/v1/bob/batch",
            json={
                "queries": [
                    {
                        "query_id": "q1",
                        "query_type": "search",
                        "params": {
                            "repo_id": mock_repo_id,
                            "query": "test",
                            "k": 5,
                        },
                    },
                    {
                        "query_id": "q2",
                        "query_type": "dependency_graph",
                        "params": {
                            "repo_id": mock_repo_id,
                            "file_path": "app.py",
                            "hops": 2,
                            "direction": "both",
                        },
                    },
                ]
            },
            headers={"Authorization": mock_auth_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert "total_queries" in data
        assert "successful_queries" in data
        assert "failed_queries" in data
        assert len(data["results"]) == 2

    def test_batch_query_too_many(
        self,
        mock_gateway,
        mock_auth_token,
        mock_repo_id,
    ):
        """Test batch query with too many sub-queries"""
        response = client.post(
            "/api/v1/bob/batch",
            json={
                "queries": [
                    {
                        "query_id": f"q{i}",
                        "query_type": "search",
                        "params": {
                            "repo_id": mock_repo_id,
                            "query": "test",
                        },
                    }
                    for i in range(21)  # Max is 20
                ]
            },
            headers={"Authorization": mock_auth_token},
        )

        assert response.status_code == 422  # Validation error


# ============================================================================
# Root Endpoints Tests
# ============================================================================


class TestRootEndpoints:
    """Test root endpoints"""

    def test_root_endpoint(self):
        """Test root endpoint"""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "service" in data
        assert "version" in data
        assert data["service"] == "IBM Bob"

    def test_readiness_probe(self):
        """Test readiness probe"""
        response = client.get("/readiness")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_liveness_probe(self):
        """Test liveness probe"""
        response = client.get("/liveness")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


# Made with Bob