"""
Unit tests for Bob tools
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from uuid import uuid4

from bob.tools.bob_tools import (
    semantic_search,
    resolve_stack_trace,
    get_dependency_graph,
    get_blast_radius,
    get_file_content,
    get_commit_diff,
    get_test_map,
    get_conventions,
    get_risk_context,
    trigger_reindex,
)
from bob.tools.client import BobClient
from bob.tools.models import (
    CodeSearchResult,
    StackFrame,
    DependencyGraph,
    BlastRadiusResult,
    FileContent,
    CommitDiff,
    RiskContext,
)
from bob.exceptions import QueryError, ResourceNotFoundError


# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def repo_id():
    """Test repository ID"""
    return str(uuid4())


@pytest.fixture
def mock_httpx_client():
    """Mock httpx client"""
    with patch("bob.tools.bob_tools.httpx.Client") as mock:
        yield mock


@pytest.fixture
def mock_graph_query():
    """Mock GraphQuery"""
    with patch("bob.tools.bob_tools.GraphQuery") as mock:
        yield mock


@pytest.fixture
def mock_file_cache():
    """Mock FileCache"""
    with patch("bob.tools.bob_tools.FileCache") as mock:
        yield mock


# ============================================================================
# Test Tool 1: Semantic Search
# ============================================================================


def test_semantic_search_success(mock_httpx_client, repo_id):
    """Test successful semantic search"""
    # Mock response
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "results": [
            {
                "file_path": "src/auth.py",
                "symbol_name": "authenticate",
                "symbol_type": "function",
                "start_line": 10,
                "end_line": 20,
                "content": "def authenticate():",
                "confidence": 0.95,
                "language": "python",
            }
        ],
        "total": 1,
    }
    
    mock_client = Mock()
    mock_client.post.return_value = mock_response
    mock_httpx_client.return_value.__enter__.return_value = mock_client
    
    # Execute
    results = semantic_search("authentication", repo_id, k=10)
    
    # Assert
    assert len(results) == 1
    assert isinstance(results[0], CodeSearchResult)
    assert results[0].file_path == "src/auth.py"
    assert results[0].confidence == 0.95


def test_semantic_search_empty_results(mock_httpx_client, repo_id):
    """Test semantic search with no results"""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"results": [], "total": 0}
    
    mock_client = Mock()
    mock_client.post.return_value = mock_response
    mock_httpx_client.return_value.__enter__.return_value = mock_client
    
    results = semantic_search("nonexistent", repo_id)
    
    assert len(results) == 0


# ============================================================================
# Test Tool 2: Resolve Stack Trace
# ============================================================================


def test_resolve_stack_trace_success(mock_httpx_client, repo_id):
    """Test successful stack trace resolution"""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "frames": [
            {
                "file_path": "src/app.py",
                "line_number": 42,
                "function": "handler",
                "commit_sha": "abc123",
                "author": "john@example.com",
                "raw_frame": 'File "src/app.py", line 42, in handler',
            }
        ],
        "total_frames": 1,
        "resolved_frames": 1,
    }
    
    mock_client = Mock()
    mock_client.post.return_value = mock_response
    mock_httpx_client.return_value.__enter__.return_value = mock_client
    
    trace = 'File "src/app.py", line 42, in handler'
    frames = resolve_stack_trace(trace, repo_id)
    
    assert len(frames) == 1
    assert isinstance(frames[0], StackFrame)
    assert frames[0].file_path == "src/app.py"
    assert frames[0].line_number == 42


# ============================================================================
# Test Tool 3: Get Dependency Graph
# ============================================================================


def test_get_dependency_graph_success(mock_httpx_client, repo_id):
    """Test successful dependency graph retrieval"""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "root_file": "src/main.py",
        "edges": [
            {
                "source": "src/utils.py",
                "target": "src/main.py",
                "relationship": "imports",
            }
        ],
        "node_count": 2,
        "edge_count": 1,
    }
    
    mock_client = Mock()
    mock_client.get.return_value = mock_response
    mock_httpx_client.return_value.__enter__.return_value = mock_client
    
    graph = get_dependency_graph("src/main.py", repo_id, hops=3)
    
    assert isinstance(graph, DependencyGraph)
    assert graph.root_file == "src/main.py"
    assert len(graph.edges) == 1
    assert graph.node_count >= 2


# ============================================================================
# Test Tool 4: Get Blast Radius
# ============================================================================


def test_get_blast_radius_success(mock_httpx_client, repo_id):
    """Test successful blast radius computation"""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "changed_files": ["src/db.py"],
        "impacted_files": [
            {
                "file_path": "src/api.py",
                "distance": 1,
                "acs_score": 0.85,
                "downstream_services": ["service-a"],
                "test_files": ["tests/test_api.py"],
            }
        ],
        "total_impacted": 1,
        "affected_services": ["service-a"],
    }
    
    mock_client = Mock()
    mock_client.post.return_value = mock_response
    mock_httpx_client.return_value.__enter__.return_value = mock_client
    
    result = get_blast_radius(["src/db.py"], repo_id)
    
    assert isinstance(result, BlastRadiusResult)
    assert len(result.impacted_files) == 1
    assert result.impacted_files[0].acs_score == 0.85


# ============================================================================
# Test Tool 5: Get File Content
# ============================================================================


def test_get_file_content_success(mock_httpx_client, repo_id):
    """Test successful file content retrieval"""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "file_path": "src/main.py",
        "content": "def main():\n    pass",
        "language": "python",
        "total_lines": 2,
        "symbols": [
            {
                "name": "main",
                "type": "function",
                "start_line": 1,
                "end_line": 2,
            }
        ],
        "imports": [],
    }
    
    mock_client = Mock()
    mock_client.get.return_value = mock_response
    mock_httpx_client.return_value.__enter__.return_value = mock_client
    
    content = get_file_content("src/main.py", repo_id)
    
    assert isinstance(content, FileContent)
    assert content.file_path == "src/main.py"
    assert content.language == "python"
    assert len(content.symbols) == 1


def test_get_file_content_not_found(mock_httpx_client, repo_id):
    """Test file not found"""
    mock_response = Mock()
    mock_response.status_code = 404
    
    mock_client = Mock()
    mock_client.get.return_value = mock_response
    mock_httpx_client.return_value.__enter__.return_value = mock_client
    
    with pytest.raises(ResourceNotFoundError):
        get_file_content("nonexistent.py", repo_id)


# ============================================================================
# Test Tool 6: Get Commit Diff
# ============================================================================


def test_get_commit_diff_success(mock_httpx_client, repo_id):
    """Test successful commit diff retrieval"""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "commit_sha": "abc123",
        "author": "john@example.com",
        "message": "Fix bug",
        "changed_files": [
            {
                "file_path": "src/main.py",
                "change_type": "modified",
                "additions": 5,
                "deletions": 2,
                "impacted_files": [],
                "test_files": [],
            }
        ],
        "total_additions": 5,
        "total_deletions": 2,
    }
    
    mock_client = Mock()
    mock_client.get.return_value = mock_response
    mock_httpx_client.return_value.__enter__.return_value = mock_client
    
    diff = get_commit_diff("abc123", repo_id)
    
    assert isinstance(diff, CommitDiff)
    assert diff.commit_sha == "abc123"
    assert len(diff.changed_files) == 1


# ============================================================================
# Test Tool 7: Get Test Map
# ============================================================================


def test_get_test_map_success(mock_graph_query, repo_id):
    """Test successful test map retrieval"""
    mock_query = Mock()
    mock_query.get_dependencies.return_value = {
        "downstream": ["tests/test_main.py", "tests/test_utils.py"]
    }
    mock_graph_query.return_value.__enter__.return_value = mock_query
    
    tests = get_test_map(["src/main.py"], repo_id)
    
    assert isinstance(tests, list)
    assert len(tests) == 2
    assert all("test" in t for t in tests)


# ============================================================================
# Test Tool 8: Get Conventions
# ============================================================================


def test_get_conventions_success(mock_file_cache, repo_id):
    """Test successful conventions retrieval"""
    mock_cache = Mock()
    mock_cache.get.return_value = None  # Cache miss
    mock_cache.set.return_value = None
    mock_file_cache.return_value.__enter__.return_value = mock_cache
    
    conventions = get_conventions("services/auth", repo_id)
    
    assert isinstance(conventions, dict)
    assert "naming" in conventions
    assert "error_handling" in conventions


# ============================================================================
# Test Tool 9: Get Risk Context
# ============================================================================


def test_get_risk_context_success(mock_graph_query, repo_id):
    """Test successful risk context retrieval"""
    mock_query = Mock()
    mock_query.get_file_metrics.return_value = {
        "fan_in": 5,
        "fan_out": 3,
    }
    mock_query.get_dependencies.return_value = {
        "downstream": ["file1.py", "file2.py"]
    }
    mock_graph_query.return_value.__enter__.return_value = mock_query
    
    contexts = get_risk_context(["src/main.py"], repo_id)
    
    assert isinstance(contexts, list)
    assert len(contexts) == 1
    assert isinstance(contexts[0], RiskContext)
    assert contexts[0].risk_level in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]


# ============================================================================
# Test Tool 10: Trigger Reindex
# ============================================================================


def test_trigger_reindex_success(mock_file_cache, repo_id):
    """Test successful reindex trigger"""
    mock_cache = Mock()
    mock_cache.redis_client = Mock()
    mock_cache.redis_client.lpush.return_value = None
    mock_cache.set.return_value = None
    mock_file_cache.return_value.__enter__.return_value = mock_cache
    
    job_id = trigger_reindex(repo_id, scope="incremental")
    
    assert isinstance(job_id, str)
    assert len(job_id) > 0


def test_trigger_reindex_invalid_scope(mock_file_cache, repo_id):
    """Test reindex with invalid scope"""
    mock_cache = Mock()
    mock_file_cache.return_value.__enter__.return_value = mock_cache
    
    with pytest.raises(QueryError):
        trigger_reindex(repo_id, scope="invalid")


# ============================================================================
# Test BobClient
# ============================================================================


def test_bob_client_initialization():
    """Test BobClient initialization"""
    client = BobClient(
        base_url="http://localhost:8000",
        api_key="test-key",
        timeout=30.0,
    )
    
    assert client.base_url == "http://localhost:8000"
    assert client.api_key == "test-key"
    assert client.timeout == 30.0


def test_bob_client_context_manager():
    """Test BobClient as context manager"""
    with BobClient() as client:
        assert client._sync_client is not None
    
    # Client should be closed after context
    assert client._sync_client is None


@pytest.mark.asyncio
async def test_bob_client_async_context_manager():
    """Test BobClient as async context manager"""
    async with BobClient() as client:
        assert client._async_client is not None
    
    # Client should be closed after context
    assert client._async_client is None


def test_bob_client_semantic_search(mock_httpx_client, repo_id):
    """Test BobClient semantic_search method"""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "results": [
            {
                "file_path": "src/auth.py",
                "symbol_name": "authenticate",
                "symbol_type": "function",
                "start_line": 10,
                "end_line": 20,
                "content": "def authenticate():",
                "confidence": 0.95,
                "language": "python",
            }
        ]
    }
    
    mock_client = Mock()
    mock_client.post.return_value = mock_response
    mock_httpx_client.return_value = mock_client
    
    client = BobClient()
    results = client.semantic_search("auth", repo_id)
    
    assert len(results) == 1
    assert results[0].symbol_name == "authenticate"


# ============================================================================
# Test Error Handling
# ============================================================================


def test_semantic_search_timeout(mock_httpx_client, repo_id):
    """Test semantic search timeout handling"""
    import httpx
    
    mock_client = Mock()
    mock_client.post.side_effect = httpx.TimeoutException("Timeout")
    mock_httpx_client.return_value.__enter__.return_value = mock_client
    
    with pytest.raises(Exception):  # Should raise QueryTimeoutError
        semantic_search("query", repo_id)


def test_semantic_search_http_error(mock_httpx_client, repo_id):
    """Test semantic search HTTP error handling"""
    import httpx
    
    mock_client = Mock()
    mock_client.post.side_effect = httpx.HTTPError("Server error")
    mock_httpx_client.return_value.__enter__.return_value = mock_client
    
    with pytest.raises(Exception):  # Should raise QueryError
        semantic_search("query", repo_id)


# Made with Bob