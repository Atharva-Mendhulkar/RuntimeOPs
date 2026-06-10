"""
IBM Bob - Integration Tests for gRPC Server
Tests for all 8 gRPC RPC methods with mocked REST handlers
"""

import json
from unittest.mock import Mock, patch
from uuid import uuid4

import grpc
import pytest

from bob.api import bob_pb2, bob_pb2_grpc
from bob.api.models import (
    BatchResponse,
    BlastRadiusResponse,
    ChangedFile,
    CommitDiffResponse,
    DependencyEdge,
    DependencyGraphResponse,
    FileResponse,
    FileSymbol,
    HealthResponse,
    ImpactedFile,
    SearchResponse,
    SearchResult,
    StackFrame,
    StackTraceResponse,
    SubQueryResult,
)
from bob.config import get_settings

settings = get_settings()


@pytest.fixture(scope="module")
def mock_auth_token():
    """Mock JWT token for authentication"""
    return "Bearer mock_token_12345"


@pytest.fixture(scope="module")
def mock_repo_id():
    """Mock repository UUID"""
    return str(uuid4())


@pytest.fixture
def mock_gateway():
    """Mock query gateway"""
    with patch("bob.api.grpc_server.get_gateway") as mock:
        gateway = Mock()
        gateway.verify_token = Mock(
            return_value={
                "repo_id": str(uuid4()),
                "org_id": "test_org",
                "exp": 9999999999,
            }
        )
        gateway.check_rate_limit = Mock()
        mock.return_value = gateway
        yield gateway


@pytest.fixture(autouse=True)
def mock_settings_port():
    """Use a non-conflicting port for testing gRPC"""
    with patch.object(settings, "grpc_port", 50053):
        yield


@pytest.fixture
async def grpc_stub():
    """
    Starts gRPC server explicitly and yields a gRPC stub connected to it.
    """
    from bob.api.grpc_server import GRPCServer

    # Start the server on the test port
    server = GRPCServer(host="127.0.0.1", port=settings.grpc_port)
    await server.start()

    channel = grpc.aio.insecure_channel(f"127.0.0.1:{settings.grpc_port}")
    stub = bob_pb2_grpc.BobServiceStub(channel)

    yield stub

    await channel.close()
    await server.stop(grace=0.1)


@pytest.mark.asyncio
class TestGRPCServer:
    """Integration test suite for the gRPC Server"""

    @patch("bob.api.grpc_server.search_code")
    async def test_search_success(
        self,
        mock_search,
        mock_gateway,
        mock_auth_token,
        mock_repo_id,
        grpc_stub,
    ):
        """Test successful Search RPC"""
        mock_search.return_value = SearchResponse(
            results=[
                SearchResult(
                    file_path="src/auth.py",
                    symbol_name="authenticate",
                    symbol_type="function",
                    start_line=10,
                    end_line=20,
                    content="def authenticate(): pass",
                    confidence=0.95,
                    language="python",
                )
            ],
            total=1,
            query_time_ms=12.5,
            repo_id=mock_repo_id,
        )

        metadata = [("authorization", mock_auth_token)]
        request = bob_pb2.SearchRequest(
            repo_id=mock_repo_id, query="auth functions", k=5, filter={"language": "python"}
        )

        response = await grpc_stub.Search(request, metadata=metadata)

        assert response.repo_id == mock_repo_id
        assert len(response.results) == 1
        assert response.results[0].file_path == "src/auth.py"
        assert response.results[0].symbol_name == "authenticate"
        assert response.results[0].confidence == 0.95

    @patch("bob.api.grpc_server.search_code")
    async def test_search_unauthorized(self, mock_search, mock_gateway, grpc_stub):
        """Test Search RPC fails if unauthorized"""
        from bob.exceptions import AuthenticationError

        mock_gateway.verify_token.side_effect = AuthenticationError("Unauthorized")

        request = bob_pb2.SearchRequest(repo_id=str(uuid4()), query="test", k=5)

        with pytest.raises(grpc.RpcError) as exc_info:
            await grpc_stub.Search(request)

        assert exc_info.value.code() == grpc.StatusCode.UNAUTHENTICATED
        assert "Unauthorized" in exc_info.value.details()

    @patch("bob.api.grpc_server.search_code")
    async def test_search_rate_limited(self, mock_search, mock_gateway, mock_auth_token, grpc_stub):
        """Test Search RPC fails if rate limit exceeded"""
        from bob.exceptions import RateLimitExceededError

        mock_gateway.check_rate_limit.side_effect = RateLimitExceededError("Rate limit exceeded")

        request = bob_pb2.SearchRequest(repo_id=str(uuid4()), query="test", k=5)

        metadata = [("authorization", mock_auth_token)]
        with pytest.raises(grpc.RpcError) as exc_info:
            await grpc_stub.Search(request, metadata=metadata)

        assert exc_info.value.code() == grpc.StatusCode.RESOURCE_EXHAUSTED
        assert "Rate limit exceeded" in exc_info.value.details()

    @patch("bob.api.grpc_server.resolve_stack_trace")
    async def test_resolve_stack_trace_success(
        self,
        mock_resolve,
        mock_gateway,
        mock_auth_token,
        mock_repo_id,
        grpc_stub,
    ):
        """Test successful ResolveStackTrace RPC"""
        mock_resolve.return_value = StackTraceResponse(
            frames=[
                StackFrame(
                    file_path="app.py",
                    line_number=42,
                    function="handler",
                    author="Alice",
                    commit_sha="abc1234",
                    commit_date="2024-02-01T00:00:00Z",
                    raw_frame='File "app.py", line 42, in handler\n    process_request()',
                )
            ],
            total_frames=1,
            resolved_frames=1,
            repo_id=mock_repo_id,
        )

        metadata = [("authorization", mock_auth_token)]
        request = bob_pb2.StackTraceRequest(
            repo_id=mock_repo_id, trace='File "app.py", line 42, in handler\n    process_request()'
        )

        response = await grpc_stub.ResolveStackTrace(request, metadata=metadata)

        assert response.repo_id == mock_repo_id
        assert len(response.frames) > 0
        assert response.frames[0].author == "Alice"
        assert response.frames[0].commit_sha == "abc1234"

    @patch("bob.api.grpc_server.get_dependency_graph")
    async def test_get_dependency_graph_success(
        self,
        mock_get_dep,
        mock_gateway,
        mock_auth_token,
        mock_repo_id,
        grpc_stub,
    ):
        """Test successful GetDependencyGraph RPC"""
        mock_get_dep.return_value = DependencyGraphResponse(
            root_file="src/main.py",
            edges=[
                DependencyEdge(source="src/main.py", target="src/utils.py", relationship="imports")
            ],
            node_count=2,
            edge_count=1,
            max_hops=3,
            repo_id=mock_repo_id,
        )

        metadata = [("authorization", mock_auth_token)]
        request = bob_pb2.DependencyGraphRequest(
            repo_id=mock_repo_id, file_path="src/main.py", hops=3, direction="both"
        )

        response = await grpc_stub.GetDependencyGraph(request, metadata=metadata)

        assert response.root_file == "src/main.py"
        assert len(response.edges) == 1
        assert response.edges[0].source == "src/main.py"
        assert response.edges[0].target == "src/utils.py"

    @patch("bob.api.grpc_server.compute_blast_radius")
    async def test_compute_blast_radius_success(
        self,
        mock_compute,
        mock_gateway,
        mock_auth_token,
        mock_repo_id,
        grpc_stub,
    ):
        """Test successful ComputeBlastRadius RPC"""
        mock_compute.return_value = BlastRadiusResponse(
            changed_files=["src/main.py"],
            impacted_files=[
                ImpactedFile(
                    file_path="src/utils.py",
                    distance=1,
                    acs_score=0.8,
                    downstream_services=["auth-service"],
                    test_files=["tests/test_utils.py"],
                )
            ],
            total_impacted=1,
            affected_services=["auth-service"],
            repo_id=mock_repo_id,
        )

        metadata = [("authorization", mock_auth_token)]
        request = bob_pb2.BlastRadiusRequest(repo_id=mock_repo_id, files=["src/main.py"])

        response = await grpc_stub.ComputeBlastRadius(request, metadata=metadata)

        assert response.repo_id == mock_repo_id
        assert response.changed_files == ["src/main.py"]
        assert len(response.impacted_files) == 1
        assert response.impacted_files[0].file_path == "src/utils.py"
        assert response.impacted_files[0].acs_score == 0.8

    @patch("bob.api.grpc_server.get_file")
    async def test_get_file_success(
        self,
        mock_get_file,
        mock_gateway,
        mock_auth_token,
        mock_repo_id,
        grpc_stub,
    ):
        """Test successful GetFile RPC"""
        mock_get_file.return_value = FileResponse(
            file_path="src/main.py",
            content="def process(): pass",
            language="python",
            total_lines=1,
            symbols=[FileSymbol(name="process", type="function", start_line=5, end_line=12)],
            imports=["os"],
            last_modified="2024-02-01T12:00:00Z",
            repo_id=mock_repo_id,
        )

        metadata = [("authorization", mock_auth_token)]
        request = bob_pb2.FileRequest(repo_id=mock_repo_id, file_path="src/main.py")

        response = await grpc_stub.GetFile(request, metadata=metadata)

        assert response.file_path == "src/main.py"
        assert response.content == "def process(): pass"
        assert len(response.symbols) == 1
        assert response.symbols[0].name == "process"

    @patch("bob.api.grpc_server.analyze_commit_diff")
    async def test_get_commit_diff_success(
        self,
        mock_analyze_diff,
        mock_gateway,
        mock_auth_token,
        mock_repo_id,
        grpc_stub,
    ):
        """Test successful GetCommitDiff RPC"""
        mock_analyze_diff.return_value = CommitDiffResponse(
            commit_sha="abcdef123456",
            author="Bob",
            message="Initial commit",
            timestamp="2024-02-01T12:00:00Z",
            changed_files=[
                ChangedFile(
                    file_path="src/auth.py",
                    additions=10,
                    deletions=2,
                    change_type="modified",
                )
            ],
            total_additions=10,
            total_deletions=2,
            repo_id=mock_repo_id,
        )

        metadata = [("authorization", mock_auth_token)]
        request = bob_pb2.CommitDiffRequest(repo_id=mock_repo_id, commit_sha="abcdef123456")

        response = await grpc_stub.GetCommitDiff(request, metadata=metadata)

        assert response.commit_sha == "abcdef123456"
        assert len(response.changed_files) == 1
        assert response.changed_files[0].file_path == "src/auth.py"
        assert response.total_additions == 10

    @patch("bob.api.grpc_server.health_check")
    async def test_get_health_success(self, mock_health, grpc_stub):
        """Test successful GetHealth RPC"""
        mock_health.return_value = HealthResponse(
            status="healthy",
            version="1.0.0",
            services={
                "postgres": "healthy",
                "redis": "healthy",
                "neo4j": "healthy",
                "weaviate": "healthy",
            },
            metrics={},
            repos_indexed=0,
            query_p95_ms=0.0,
            index_queue_depth=0,
            timestamp=1700000000.0,
        )

        request = bob_pb2.HealthRequest()
        response = await grpc_stub.GetHealth(request)

        assert response.status == "healthy"
        assert response.version == "1.0.0"
        assert "postgres" in response.services

    @patch("bob.api.grpc_server.batch_query")
    async def test_batch_success(
        self,
        mock_batch,
        mock_gateway,
        mock_auth_token,
        mock_repo_id,
        grpc_stub,
    ):
        """Test successful Batch RPC processing multiple subqueries"""
        mock_batch.return_value = BatchResponse(
            results=[
                SubQueryResult(
                    query_id="q1",
                    success=True,
                    result={"file_path": "src/main.py", "content": "def test(): pass"},
                    error=None,
                    execution_time_ms=1.5,
                )
            ],
            total_queries=1,
            successful_queries=1,
            failed_queries=0,
            total_time_ms=1.5,
        )

        metadata = [("authorization", mock_auth_token)]
        request = bob_pb2.BatchRequest(
            queries=[
                bob_pb2.SubQuery(
                    query_id="q1",
                    query_type="file",
                    params_json=json.dumps({"repo_id": mock_repo_id, "file_path": "src/main.py"}),
                )
            ]
        )

        response = await grpc_stub.Batch(request, metadata=metadata)

        assert response.total_queries == 1
        assert response.successful_queries == 1
        assert len(response.results) == 1
        assert response.results[0].query_id == "q1"
        assert response.results[0].success is True

        result_data = json.loads(response.results[0].result_json)
        assert result_data["file_path"] == "src/main.py"
        assert result_data["content"] == "def test(): pass"
