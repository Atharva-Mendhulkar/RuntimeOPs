"""
IBM Bob - Unit Tests for API Layer
Tests for API models, gateway, router, and assembler
"""

from uuid import uuid4

import pytest

from bob.api.models import (
    BatchRequest,
    BlastRadiusRequest,
    DependencyGraphRequest,
    SearchRequest,
    StackTraceRequest,
    SubQuery,
)
from bob.query.assembler import AssembledResult, Evidence, ResultAssembler
from bob.query.router import QueryRouter, QueryType

# ============================================================================
# API Models Tests
# ============================================================================


class TestAPIModels:
    """Test API request/response models"""

    def test_search_request_validation(self):
        """Test SearchRequest validation"""
        # Valid request
        request = SearchRequest(
            repo_id=uuid4(),
            query="authentication middleware",
            k=10,
        )
        assert request.k == 10
        assert len(request.query) > 0

        # Invalid k (too large)
        with pytest.raises(ValueError):
            SearchRequest(
                repo_id=uuid4(),
                query="test",
                k=100,  # Max is 50
            )

        # Invalid query (too short)
        with pytest.raises(ValueError):
            SearchRequest(
                repo_id=uuid4(),
                query="ab",  # Min length is 3
                k=10,
            )

    def test_stack_trace_request_validation(self):
        """Test StackTraceRequest validation"""
        request = StackTraceRequest(
            repo_id=uuid4(),
            trace="Traceback (most recent call last):\n  File 'app.py', line 42",
        )
        assert len(request.trace) >= 10

    def test_dependency_graph_request_validation(self):
        """Test DependencyGraphRequest validation"""
        request = DependencyGraphRequest(
            repo_id=uuid4(),
            file_path="src/app.py",
            hops=3,
            direction="both",
        )
        assert request.hops == 3
        assert request.direction in ("upstream", "downstream", "both")

    def test_blast_radius_request_validation(self):
        """Test BlastRadiusRequest validation"""
        request = BlastRadiusRequest(
            repo_id=uuid4(),
            files=["src/auth.py", "src/db.py"],
        )
        assert len(request.files) >= 1

        # Invalid: too many files
        with pytest.raises(ValueError):
            BlastRadiusRequest(
                repo_id=uuid4(),
                files=["file.py"] * 101,  # Max is 100
            )

    def test_batch_request_validation(self):
        """Test BatchRequest validation"""
        request = BatchRequest(
            queries=[
                SubQuery(
                    query_id="q1",
                    query_type="search",
                    params={"repo_id": str(uuid4()), "query": "test", "k": 10},
                ),
                SubQuery(
                    query_id="q2",
                    query_type="file",
                    params={"repo_id": str(uuid4()), "file_path": "app.py"},
                ),
            ]
        )
        assert len(request.queries) == 2

        # Invalid: too many queries
        with pytest.raises(ValueError):
            BatchRequest(
                queries=[
                    SubQuery(
                        query_id=f"q{i}",
                        query_type="search",
                        params={"repo_id": str(uuid4()), "query": "test"},
                    )
                    for i in range(21)  # Max is 20
                ]
            )


# ============================================================================
# Query Router Tests
# ============================================================================


class TestQueryRouter:
    """Test query router"""

    def setup_method(self):
        """Setup test fixtures"""
        self.router = QueryRouter()
        self.repo_id = uuid4()

    def test_classify_semantic_query(self):
        """Test semantic query classification"""
        query = "find authentication middleware function"
        query_type = self.router.classify_query(query)
        assert query_type == QueryType.SEMANTIC

    def test_classify_graph_query(self):
        """Test graph query classification"""
        query = "show me dependencies for this file"
        query_type = self.router.classify_query(query)
        assert query_type == QueryType.GRAPH

    def test_classify_with_context(self):
        """Test query classification with context"""
        query = "test query"

        # Semantic context
        query_type = self.router.classify_query(
            query,
            context={"endpoint": "search"},
        )
        assert query_type == QueryType.SEMANTIC

        # Graph context
        query_type = self.router.classify_query(
            query,
            context={"endpoint": "dependency-graph"},
        )
        assert query_type == QueryType.GRAPH

    def test_route_search_query(self):
        """Test search query routing"""
        routing = self.router.route_search_query(
            repo_id=self.repo_id,
            query="authentication",
            k=10,
        )

        assert routing["backend"] == "weaviate"
        assert routing["params"]["k"] == 10
        assert "optimization" in routing

    def test_route_graph_query(self):
        """Test graph query routing"""
        routing = self.router.route_graph_query(
            repo_id=self.repo_id,
            operation="dependencies",
            params={"file_path": "app.py", "max_hops": 3},
        )

        assert routing["backend"] == "neo4j"
        assert routing["operation"] == "dependencies"
        assert "optimization" in routing

    def test_route_file_query(self):
        """Test file query routing"""
        routing = self.router.route_file_query(
            repo_id=self.repo_id,
            file_path="src/app.py",
        )

        assert routing["backend"] == "redis"
        assert routing["fallback"] == "git"
        assert routing["params"]["file_path"] == "src/app.py"

    def test_route_hybrid_query(self):
        """Test hybrid query routing"""
        routing = self.router.route_hybrid_query(
            repo_id=self.repo_id,
            query="authentication",
            k=10,
            graph_hops=3,
        )

        assert routing["query_type"] == QueryType.HYBRID.value
        assert "weaviate" in routing["backends"]
        assert "neo4j" in routing["backends"]
        assert len(routing["stages"]) == 2

    def test_should_use_cache(self):
        """Test cache decision logic"""
        # File queries should always use cache
        assert self.router.should_use_cache(
            QueryType.FILE,
            {"file_path": "app.py"},
        )

        # Graph queries for expensive operations should use cache
        assert self.router.should_use_cache(
            QueryType.GRAPH,
            {"operation": "blast_radius"},
        )

        # Semantic queries with long queries should use cache
        assert self.router.should_use_cache(
            QueryType.SEMANTIC,
            {"query": "find all authentication middleware functions in the codebase"},
        )

    def test_estimate_query_cost(self):
        """Test query cost estimation"""
        # Semantic query cost
        cost = self.router.estimate_query_cost(
            QueryType.SEMANTIC,
            {"k": 10},
        )
        assert cost["estimated_time_ms"] > 0
        assert cost["complexity"] in ("low", "medium", "high")

        # Graph query cost
        cost = self.router.estimate_query_cost(
            QueryType.GRAPH,
            {"operation": "blast_radius", "max_hops": 5},
        )
        assert cost["estimated_time_ms"] > 0
        assert cost["complexity"] in ("low", "medium", "high")


# ============================================================================
# Result Assembler Tests
# ============================================================================


class TestResultAssembler:
    """Test result assembler"""

    def setup_method(self):
        """Setup test fixtures"""
        self.assembler = ResultAssembler(enable_reranking=False)
        self.repo_id = uuid4()

    def test_calculate_centrality(self):
        """Test centrality calculation"""
        # High centrality
        metadata = {"fan_in": 20, "fan_out": 15}
        centrality = self.assembler._calculate_centrality(metadata)
        assert 0.0 <= centrality <= 1.0
        assert centrality > 0.5

        # Low centrality
        metadata = {"fan_in": 2, "fan_out": 1}
        centrality = self.assembler._calculate_centrality(metadata)
        assert 0.0 <= centrality <= 1.0
        assert centrality < 0.2

        # Empty metadata
        centrality = self.assembler._calculate_centrality({})
        assert centrality == 0.0

    def test_calculate_confidence(self):
        """Test confidence score calculation"""
        metadata = {
            "vector_similarity": 0.9,
            "rerank_score": 0.0,
            "graph_centrality": 0.7,
        }

        confidence = self.assembler._calculate_confidence(metadata)
        assert 0.0 <= confidence <= 1.0

        # Should be weighted combination
        expected = (0.9 * 0.50) + (0.7 * 0.50)  # No reranking
        assert abs(confidence - expected) < 0.01

    def test_calculate_confidence_with_reranking(self):
        """Test confidence score with reranking enabled"""
        assembler = ResultAssembler(enable_reranking=True)

        metadata = {
            "vector_similarity": 0.9,
            "rerank_score": 0.85,
            "graph_centrality": 0.7,
        }

        confidence = assembler._calculate_confidence(metadata)
        assert 0.0 <= confidence <= 1.0

        # Should include rerank score
        expected = (0.9 * 0.50) + (0.85 * 0.35) + (0.7 * 0.15)
        assert abs(confidence - expected) < 0.01

    def test_trim_to_token_budget(self):
        """Test token budget trimming"""
        # Create mock results
        results = [
            AssembledResult(
                file_path=f"file{i}.py",
                symbol_name=f"function{i}",
                symbol_type="function",
                start_line=1,
                end_line=10,
                content="def function(): pass" * 100,  # Large content
                language="python",
                confidence=0.9 - (i * 0.1),
                evidence=Evidence(
                    file_path=f"file{i}.py",
                    line_range=(1, 10),
                ),
                metadata={},
            )
            for i in range(20)
        ]

        trimmed = self.assembler._trim_to_token_budget(results)

        # Should trim to fit budget
        assert len(trimmed) < len(results)
        assert len(trimmed) > 0

    def test_filter_by_confidence(self):
        """Test confidence filtering"""
        results = [
            AssembledResult(
                file_path=f"file{i}.py",
                symbol_name=f"function{i}",
                symbol_type="function",
                start_line=1,
                end_line=10,
                content="def function(): pass",
                language="python",
                confidence=0.5 + (i * 0.1),
                evidence=Evidence(
                    file_path=f"file{i}.py",
                    line_range=(1, 10),
                ),
                metadata={},
            )
            for i in range(5)
        ]

        filtered = self.assembler.filter_by_confidence(results, min_confidence=0.7)

        # Should only include results with confidence >= 0.7
        assert all(r.confidence >= 0.7 for r in filtered)
        assert len(filtered) < len(results)

    def test_deduplicate_results(self):
        """Test result deduplication"""
        # Create duplicate results
        results = [
            AssembledResult(
                file_path="file.py",
                symbol_name="function",
                symbol_type="function",
                start_line=1,
                end_line=10,
                content="def function(): pass",
                language="python",
                confidence=0.9,
                evidence=Evidence(
                    file_path="file.py",
                    line_range=(1, 10),
                ),
                metadata={},
            )
            for _ in range(3)
        ]

        # Add a unique result
        results.append(
            AssembledResult(
                file_path="other.py",
                symbol_name="other_function",
                symbol_type="function",
                start_line=1,
                end_line=10,
                content="def other_function(): pass",
                language="python",
                confidence=0.8,
                evidence=Evidence(
                    file_path="other.py",
                    line_range=(1, 10),
                ),
                metadata={},
            )
        )

        deduplicated = self.assembler.deduplicate_results(results)

        # Should remove duplicates
        assert len(deduplicated) == 2

    def test_format_for_response(self):
        """Test response formatting"""
        results = [
            AssembledResult(
                file_path="file.py",
                symbol_name="function",
                symbol_type="function",
                start_line=1,
                end_line=10,
                content="def function(): pass",
                language="python",
                confidence=0.9,
                evidence=Evidence(
                    file_path="file.py",
                    line_range=(1, 10),
                    commit_sha="abc123",
                    author="John Doe",
                    last_modified="2024-01-01T00:00:00Z",
                ),
                metadata={
                    "dependency_count": 5,
                    "acs_score": 0.7,
                    "total_lines": 100,
                },
            )
        ]

        formatted = self.assembler.format_for_response(results)

        assert len(formatted) == 1
        assert formatted[0]["file_path"] == "file.py"
        assert formatted[0]["confidence"] == 0.9
        assert "evidence" in formatted[0]
        assert "metadata" in formatted[0]


# Made with Bob
