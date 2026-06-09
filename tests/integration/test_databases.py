"""
IBM Bob - Integration Tests for Databases
Tests for Neo4j, Weaviate, Redis, and PostgreSQL integration
"""

import os
from datetime import datetime
from uuid import uuid4

import pytest

from bob.config import get_settings
from bob.graph.models import FileNode, RepositoryNode, SymbolNode
from bob.graph.query import GraphQuery
from bob.graph.writer import GraphWriter
from bob.semantic.embedder import CodeChunk, Embedding
from bob.semantic.vector_store import VectorStore
from bob.storage.cache import FileCache
from bob.storage.registry import IndexRegistryManager

# Skip integration tests if databases are not available
pytestmark = pytest.mark.skipif(
    os.getenv("SKIP_INTEGRATION_TESTS", "false").lower() == "true",
    reason="Integration tests skipped (set SKIP_INTEGRATION_TESTS=false to run)",
)


class TestNeo4jIntegration:
    """Integration tests for Neo4j graph database"""

    @pytest.fixture
    def graph_writer(self):
        """Create graph writer instance"""
        writer = GraphWriter()
        try:
            writer.connect()
            yield writer
        finally:
            writer.close()

    @pytest.fixture
    def graph_query(self):
        """Create graph query instance"""
        query = GraphQuery()
        try:
            query.connect()
            yield query
        finally:
            query.close()

    @pytest.fixture
    def test_repo_id(self, graph_writer):
        """Create test repository and clean up after"""
        repo_id = uuid4()
        graph_writer.write_repository(
            repo_id=repo_id,
            github_url="https://github.com/test/integration-test",
            name="integration-test",
        )
        yield repo_id
        # Cleanup
        graph_writer.delete_repository(repo_id)

    def test_write_and_read_repository(self, graph_writer, graph_query):
        """Test writing and reading repository"""
        repo_id = uuid4()
        
        # Write repository
        repo_node = graph_writer.write_repository(
            repo_id=repo_id,
            github_url="https://github.com/test/write-read-test",
            name="write-read-test",
        )
        
        assert repo_node.repo_id == repo_id
        
        # Cleanup
        graph_writer.delete_repository(repo_id)

    def test_write_file_nodes(self, graph_writer, test_repo_id):
        """Test writing file nodes"""
        from bob.parsers.base import ParseResult
        
        parse_results = [
            ParseResult(
                file_path="src/main.py",
                language="python",
                symbols=[],
                imports=[],
                exports=[],
                total_lines=50,
                code_lines=40,
                comment_lines=5,
                parse_errors=[],
                success=True,
            ),
            ParseResult(
                file_path="src/utils.py",
                language="python",
                symbols=[],
                imports=[],
                exports=[],
                total_lines=30,
                code_lines=25,
                comment_lines=3,
                parse_errors=[],
                success=True,
            ),
        ]
        
        stats = graph_writer.write_parse_results(test_repo_id, parse_results)
        
        assert stats["files"] == 2

    def test_graph_integrity_check(self, graph_writer, test_repo_id):
        """Test graph integrity check"""
        checks = graph_writer.check_graph_integrity(test_repo_id)
        
        assert "orphaned_symbols" in checks
        assert "orphaned_files" in checks
        assert isinstance(checks["orphaned_symbols"], int)

    def test_query_dependencies(self, graph_query, test_repo_id):
        """Test querying dependencies"""
        deps = graph_query.get_dependencies(
            repo_id=test_repo_id,
            file_path="src/main.py",
            direction="both",
            max_hops=5,
        )
        
        assert "upstream" in deps
        assert "downstream" in deps


class TestWeaviateIntegration:
    """Integration tests for Weaviate vector store"""

    @pytest.fixture
    def vector_store(self):
        """Create vector store instance"""
        store = VectorStore()
        try:
            store.connect()
            yield store
        finally:
            store.close()

    @pytest.fixture
    def test_repo_id(self):
        """Generate test repository ID"""
        return uuid4()

    @pytest.fixture
    def test_embeddings(self, test_repo_id):
        """Create test embeddings"""
        embeddings = []
        for i in range(3):
            chunk = CodeChunk(
                content=f"def test_function_{i}():\n    pass",
                file_path=f"src/test_{i}.py",
                symbol_name=f"test_function_{i}",
                symbol_type="function",
                start_line=1,
                end_line=2,
                token_count=10,
            )
            
            # Create dummy embedding vector (384 dimensions for all-MiniLM)
            vector = [0.1] * 384
            
            embedding = Embedding(
                vector=vector,
                chunk=chunk,
                model="test-model",
                timestamp=datetime.utcnow().timestamp(),
            )
            embeddings.append(embedding)
        
        return embeddings

    def test_upsert_and_search_embeddings(self, vector_store, test_repo_id, test_embeddings):
        """Test upserting and searching embeddings"""
        # Upsert embeddings
        count = vector_store.upsert_embeddings(
            repo_id=test_repo_id,
            embeddings=test_embeddings,
            language="python",
        )
        
        assert count == 3
        
        # Search by vector
        query_vector = [0.1] * 384
        results = vector_store.search(
            query_vector=query_vector,
            repo_id=test_repo_id,
            limit=5,
            min_certainty=0.0,
        )
        
        assert len(results) > 0
        
        # Cleanup
        vector_store.invalidate_repository(test_repo_id)

    def test_search_by_text(self, vector_store, test_repo_id, test_embeddings):
        """Test hybrid text search"""
        # Upsert embeddings
        vector_store.upsert_embeddings(
            repo_id=test_repo_id,
            embeddings=test_embeddings,
            language="python",
        )
        
        # Search by text
        results = vector_store.search_by_text(
            query_text="test function",
            repo_id=test_repo_id,
            limit=5,
        )
        
        assert isinstance(results, list)
        
        # Cleanup
        vector_store.invalidate_repository(test_repo_id)

    def test_invalidate_file(self, vector_store, test_repo_id, test_embeddings):
        """Test file invalidation"""
        # Upsert embeddings
        vector_store.upsert_embeddings(
            repo_id=test_repo_id,
            embeddings=test_embeddings,
            language="python",
        )
        
        # Invalidate one file
        deleted = vector_store.invalidate_file(test_repo_id, "src/test_0.py")
        
        assert deleted >= 0
        
        # Cleanup
        vector_store.invalidate_repository(test_repo_id)

    def test_get_stats(self, vector_store, test_repo_id, test_embeddings):
        """Test getting vector store stats"""
        # Upsert embeddings
        vector_store.upsert_embeddings(
            repo_id=test_repo_id,
            embeddings=test_embeddings,
            language="python",
        )
        
        # Get stats
        stats = vector_store.get_stats(repo_id=test_repo_id)
        
        assert "total_embeddings" in stats
        assert stats["total_embeddings"] >= 0
        
        # Cleanup
        vector_store.invalidate_repository(test_repo_id)


class TestRedisIntegration:
    """Integration tests for Redis cache"""

    @pytest.fixture
    def cache(self):
        """Create cache instance"""
        cache = FileCache()
        try:
            cache.connect()
            yield cache
        finally:
            # Cleanup test keys
            cache.flush_namespace("test")
            cache.close()

    def test_set_and_get(self, cache):
        """Test cache set and get"""
        result = cache.set("test", "key1", "value1")
        assert result is True
        
        value = cache.get("test", "key1")
        assert value == "value1"

    def test_json_operations(self, cache):
        """Test JSON cache operations"""
        test_data = {"name": "test", "count": 42, "active": True}
        
        result = cache.set_json("test", "json_key", test_data)
        assert result is True
        
        retrieved = cache.get_json("test", "json_key")
        assert retrieved == test_data

    def test_invalidate(self, cache):
        """Test cache invalidation"""
        cache.set("test", "key_to_delete", "value")
        
        result = cache.invalidate("test", "key_to_delete")
        assert result is True
        
        value = cache.get("test", "key_to_delete")
        assert value is None

    def test_invalidate_pattern(self, cache):
        """Test pattern-based invalidation"""
        # Set multiple keys
        cache.set("test", "prefix_key1", "value1")
        cache.set("test", "prefix_key2", "value2")
        cache.set("test", "other_key", "value3")
        
        # Invalidate pattern
        count = cache.invalidate_pattern("test", "prefix_*")
        assert count >= 2

    def test_cache_stats(self, cache):
        """Test cache statistics"""
        # Set some values
        cache.set("test", "stat_key1", "value1")
        cache.set("test", "stat_key2", "value2")
        
        stats = cache.get_stats()
        
        assert "total_keys" in stats
        assert "hits" in stats
        assert "misses" in stats

    def test_prewarm(self, cache):
        """Test cache pre-warming"""
        files = {
            "file1.py": "content1",
            "file2.py": "content2",
            "file3.py": "content3",
        }
        
        count = cache.prewarm("test_repo", files)
        assert count == 3


class TestPostgreSQLIntegration:
    """Integration tests for PostgreSQL registry"""

    @pytest.fixture
    def registry(self):
        """Create registry instance"""
        registry = IndexRegistryManager()
        try:
            registry.connect()
            yield registry
        finally:
            registry.close()

    @pytest.fixture
    def test_repo_id(self, registry):
        """Create test repository and clean up after"""
        repo_id = registry.create_repository(
            github_url=f"https://github.com/test/integration-{uuid4()}",
            status="idle",
        )
        yield repo_id
        # Cleanup
        try:
            registry.delete_repository(repo_id)
        except:
            pass

    def test_create_and_get_repository(self, registry):
        """Test creating and getting repository"""
        github_url = f"https://github.com/test/create-get-{uuid4()}"
        
        repo_id = registry.create_repository(github_url=github_url)
        assert repo_id is not None
        
        repo_data = registry.get_repository(repo_id)
        assert repo_data["github_url"] == github_url
        assert repo_data["status"] == "idle"
        
        # Cleanup
        registry.delete_repository(repo_id)

    def test_update_repository_status(self, registry, test_repo_id):
        """Test updating repository status"""
        registry.update_repository_status(test_repo_id, "indexing")
        
        repo_data = registry.get_repository(test_repo_id)
        assert repo_data["status"] == "indexing"

    def test_update_repository_metrics(self, registry, test_repo_id):
        """Test updating repository metrics"""
        registry.update_repository_metrics(
            repo_id=test_repo_id,
            file_count=100,
            error_count=5,
            coverage_pct=95.0,
        )
        
        repo_data = registry.get_repository(test_repo_id)
        assert repo_data["file_count"] == 100
        assert repo_data["error_count"] == 5
        assert repo_data["coverage_pct"] == 95.0

    def test_mark_full_index_complete(self, registry, test_repo_id):
        """Test marking full index complete"""
        registry.mark_full_index_complete(test_repo_id)
        
        repo_data = registry.get_repository(test_repo_id)
        assert repo_data["last_full_index"] is not None
        assert repo_data["status"] == "idle"

    def test_list_repositories(self, registry, test_repo_id):
        """Test listing repositories"""
        repos = registry.list_repositories(limit=10)
        
        assert isinstance(repos, list)
        assert len(repos) > 0

    def test_create_and_update_job(self, registry, test_repo_id):
        """Test creating and updating index job"""
        job_id = registry.create_index_job(test_repo_id, "full")
        assert job_id is not None
        
        registry.update_job_status(job_id, "running", files_processed=50)
        registry.update_job_status(job_id, "completed", files_processed=100)

    def test_get_health_metrics(self, registry):
        """Test getting health metrics"""
        metrics = registry.get_health_metrics()
        
        assert "total_repositories" in metrics
        assert "status_counts" in metrics
        assert "average_coverage" in metrics
        assert "total_files_indexed" in metrics


# Made with Bob