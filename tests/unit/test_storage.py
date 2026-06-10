"""
IBM Bob - Unit Tests for Storage Components
Tests for cache, registry, and storage utilities
"""

import json
from datetime import datetime
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest

from bob.storage.cache import FileCache
from bob.storage.registry import IndexRegistryManager


class TestFileCache:
    """Unit tests for FileCache"""

    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client"""
        with patch("bob.storage.cache.redis.Redis") as mock:
            redis_instance = MagicMock()
            redis_instance.ping.return_value = True
            redis_instance.get.return_value = None
            redis_instance.setex.return_value = True
            redis_instance.delete.return_value = 1
            redis_instance.keys.return_value = []
            redis_instance.dbsize.return_value = 0
            redis_instance.info.return_value = {}
            mock.return_value = redis_instance
            yield redis_instance

    @pytest.fixture
    def mock_fernet(self):
        """Mock Fernet encryption"""
        with patch("bob.storage.cache.Fernet") as mock:
            fernet_instance = MagicMock()
            fernet_instance.encrypt.return_value = b"encrypted_data"
            fernet_instance.decrypt.return_value = b"decrypted_data"
            mock.return_value = fernet_instance
            mock.generate_key.return_value = b"test_key_32_bytes_long_enough!!"
            yield fernet_instance

    def test_cache_initialization(self, mock_redis, mock_fernet):
        """Test cache initialization"""
        cache = FileCache()
        cache.connect()

        assert cache._redis_client is not None
        assert cache._cipher is not None
        mock_redis.ping.assert_called_once()

    def test_cache_set_and_get(self, mock_redis, mock_fernet):
        """Test cache set and get operations"""
        cache = FileCache()
        cache.connect()

        # Mock encrypted data
        mock_fernet.encrypt.return_value = b"encrypted_test_value"
        mock_redis.get.return_value = b"encrypted_test_value"
        mock_fernet.decrypt.return_value = b"test_value"

        # Set value
        result = cache.set("file", "test_key", "test_value")
        assert result is True
        mock_redis.setex.assert_called_once()

        # Get value
        value = cache.get("file", "test_key")
        assert value == "test_value"
        mock_redis.get.assert_called_once()

    def test_cache_invalidate(self, mock_redis, mock_fernet):
        """Test cache invalidation"""
        cache = FileCache()
        cache.connect()

        result = cache.invalidate("file", "test_key")
        assert result is True
        mock_redis.delete.assert_called_once()

    def test_cache_invalidate_pattern(self, mock_redis, mock_fernet):
        """Test pattern-based invalidation"""
        cache = FileCache()
        cache.connect()

        mock_redis.keys.return_value = [b"key1", b"key2", b"key3"]
        mock_redis.delete.return_value = 3

        count = cache.invalidate_pattern("file", "test_*")
        assert count == 3
        mock_redis.keys.assert_called_once()
        mock_redis.delete.assert_called_once()

    def test_cache_json_operations(self, mock_redis, mock_fernet):
        """Test JSON cache operations"""
        cache = FileCache()
        cache.connect()

        test_data = {"key": "value", "number": 42}
        json_str = json.dumps(test_data)

        # Mock encryption/decryption
        mock_fernet.encrypt.return_value = b"encrypted_json"
        mock_redis.get.return_value = b"encrypted_json"
        mock_fernet.decrypt.return_value = json_str.encode()

        # Set JSON
        result = cache.set_json("file", "test_key", test_data)
        assert result is True

        # Get JSON
        retrieved = cache.get_json("file", "test_key")
        assert retrieved == test_data

    def test_cache_stats(self, mock_redis, mock_fernet):
        """Test cache statistics"""
        cache = FileCache()
        cache.connect()

        mock_redis.dbsize.return_value = 100
        mock_redis.info.return_value = {
            "keyspace_hits": 80,
            "keyspace_misses": 20,
            "evicted_keys": 5,
            "expired_keys": 10,
        }

        stats = cache.get_stats()
        assert stats["total_keys"] == 100
        assert stats["hits"] == 80
        assert stats["misses"] == 20
        assert stats["hit_rate"] == 0.8

    def test_cache_prewarm(self, mock_redis, mock_fernet):
        """Test cache pre-warming"""
        cache = FileCache()
        cache.connect()

        files = {
            "file1.py": "content1",
            "file2.py": "content2",
            "file3.py": "content3",
        }

        count = cache.prewarm("repo123", files)
        assert count == 3
        assert mock_redis.setex.call_count == 3


class TestIndexRegistryManager:
    """Unit tests for IndexRegistryManager"""

    @pytest.fixture
    def mock_engine(self):
        """Mock SQLAlchemy engine"""
        with patch("bob.storage.registry.create_engine") as mock:
            engine = MagicMock()
            mock.return_value = engine
            yield engine

    @pytest.fixture
    def mock_session(self):
        """Mock SQLAlchemy session"""
        session = MagicMock()
        session.query.return_value = session
        session.filter_by.return_value = session
        session.filter.return_value = session
        session.first.return_value = None
        session.all.return_value = []
        session.scalar.return_value = 0
        return session

    @pytest.fixture
    def mock_session_factory(self, mock_session):
        """Mock session factory"""
        with patch("bob.storage.registry.sessionmaker") as mock:
            mock.return_value = lambda: mock_session
            yield mock

    def test_registry_initialization(self, mock_engine, mock_session_factory):
        """Test registry initialization"""
        registry = IndexRegistryManager()
        registry.connect()

        assert registry._engine is not None
        assert registry._session_factory is not None

    def test_create_repository(self, mock_engine, mock_session_factory, mock_session):
        """Test repository creation"""
        registry = IndexRegistryManager()
        registry.connect()

        # Mock repository object
        mock_repo = MagicMock()
        mock_repo.repo_id = uuid4()
        mock_session.add = MagicMock()
        mock_session.commit = MagicMock()

        with patch("bob.storage.registry.IndexRegistry") as mock_registry_class:
            mock_registry_class.return_value = mock_repo

            repo_id = registry.create_repository("https://github.com/test/repo")
            assert isinstance(repo_id, UUID)

    def test_get_repository(self, mock_engine, mock_session_factory, mock_session):
        """Test get repository"""
        registry = IndexRegistryManager()
        registry.connect()

        # Mock repository
        mock_repo = MagicMock()
        mock_repo.repo_id = uuid4()
        mock_repo.github_url = "https://github.com/test/repo"
        mock_repo.status = "idle"
        mock_repo.file_count = 100
        mock_repo.error_count = 0
        mock_repo.coverage_pct = 98.5
        mock_repo.created_at = datetime.utcnow()
        mock_repo.updated_at = datetime.utcnow()
        mock_repo.last_full_index = None
        mock_repo.last_incremental = None

        mock_session.first.return_value = mock_repo

        repo_data = registry.get_repository(mock_repo.repo_id)
        assert repo_data["github_url"] == "https://github.com/test/repo"
        assert repo_data["status"] == "idle"
        assert repo_data["file_count"] == 100

    def test_update_repository_status(self, mock_engine, mock_session_factory, mock_session):
        """Test update repository status"""
        registry = IndexRegistryManager()
        registry.connect()

        mock_repo = MagicMock()
        mock_repo.status = "idle"
        mock_repo.error_count = 0
        mock_session.first.return_value = mock_repo

        repo_id = uuid4()
        registry.update_repository_status(repo_id, "indexing")

        assert mock_repo.status == "indexing"
        mock_session.commit.assert_called_once()

    def test_update_repository_metrics(self, mock_engine, mock_session_factory, mock_session):
        """Test update repository metrics"""
        registry = IndexRegistryManager()
        registry.connect()

        mock_repo = MagicMock()
        mock_session.first.return_value = mock_repo

        repo_id = uuid4()
        registry.update_repository_metrics(repo_id, 150, 5, 96.7)

        assert mock_repo.file_count == 150
        assert mock_repo.error_count == 5
        assert mock_repo.coverage_pct == 96.7
        mock_session.commit.assert_called_once()

    def test_detect_stale_repositories(self, mock_engine, mock_session_factory, mock_session):
        """Test stale repository detection"""
        registry = IndexRegistryManager()
        registry.connect()

        # Mock stale repositories
        mock_repo1 = MagicMock()
        mock_repo1.repo_id = uuid4()
        mock_repo1.github_url = "https://github.com/test/repo1"
        mock_repo1.status = "idle"
        mock_repo1.last_incremental = datetime.utcnow()

        mock_session.all.return_value = [mock_repo1]

        stale_repos = registry.detect_stale_repositories(threshold_minutes=10)
        assert len(stale_repos) == 1
        assert stale_repos[0]["github_url"] == "https://github.com/test/repo1"

    def test_list_repositories(self, mock_engine, mock_session_factory, mock_session):
        """Test list repositories"""
        registry = IndexRegistryManager()
        registry.connect()

        # Mock repositories
        mock_repos = []
        for i in range(3):
            mock_repo = MagicMock()
            mock_repo.repo_id = uuid4()
            mock_repo.github_url = f"https://github.com/test/repo{i}"
            mock_repo.status = "idle"
            mock_repo.file_count = 100 + i
            mock_repo.error_count = 0
            mock_repo.coverage_pct = 98.0 + i
            mock_repo.last_full_index = None
            mock_repo.last_incremental = None
            mock_repos.append(mock_repo)

        mock_session.limit.return_value = mock_session
        mock_session.offset.return_value = mock_session
        mock_session.all.return_value = mock_repos

        repos = registry.list_repositories(limit=10)
        assert len(repos) == 3

    def test_create_index_job(self, mock_engine, mock_session_factory, mock_session):
        """Test create index job"""
        registry = IndexRegistryManager()
        registry.connect()

        mock_job = MagicMock()
        mock_job.job_id = uuid4()
        mock_session.add = MagicMock()
        mock_session.commit = MagicMock()

        with patch("bob.storage.registry.IndexJob") as mock_job_class:
            mock_job_class.return_value = mock_job

            repo_id = uuid4()
            job_id = registry.create_index_job(repo_id, "full")
            assert isinstance(job_id, UUID)

    def test_update_job_status(self, mock_engine, mock_session_factory, mock_session):
        """Test update job status"""
        registry = IndexRegistryManager()
        registry.connect()

        mock_job = MagicMock()
        mock_job.status = "pending"
        mock_job.started_at = None
        mock_job.completed_at = None
        mock_session.first.return_value = mock_job

        job_id = uuid4()
        registry.update_job_status(job_id, "running")

        assert mock_job.status == "running"
        assert mock_job.started_at is not None
        mock_session.commit.assert_called_once()

    def test_get_health_metrics(self, mock_engine, mock_session_factory, mock_session):
        """Test get health metrics"""
        registry = IndexRegistryManager()
        registry.connect()

        # Mock metrics
        mock_session.scalar.return_value = 10
        mock_session.all.return_value = []

        metrics = registry.get_health_metrics()
        assert "total_repositories" in metrics
        assert "status_counts" in metrics
        assert "average_coverage" in metrics


# Made with Bob
