"""
IBM Bob - Redis Caching Layer
Encrypted file caching using Redis with AES-256 encryption
"""

import json
import logging
from typing import Any

import redis
from cryptography.fernet import Fernet, InvalidToken

from bob.config import get_settings
from bob.exceptions import EncryptionError

logger = logging.getLogger(__name__)


class FileCache:
    """
    Redis-based file cache with AES-256 encryption.

    Responsibilities:
    - Cache file contents with encryption
    - Cache convention data
    - LRU eviction policy monitoring
    - TTL management (1 hour for files, 24 hours for conventions)
    - Cache pre-warming for active repositories
    """

    def __init__(self) -> None:
        """Initialize the file cache"""
        self.settings = get_settings()
        self._redis_client: redis.Redis | None = None
        self._cipher: Fernet | None = None
        self._file_ttl = self.settings.file_cache_ttl_seconds
        self._convention_ttl = self.settings.convention_cache_ttl_seconds

    def __enter__(self) -> "FileCache":
        """Context manager entry"""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit"""
        self.close()

    def connect(self) -> None:
        """Connect to Redis and initialize encryption"""
        try:
            # Connect to Redis
            self._redis_client = redis.Redis(
                host=self.settings.redis_host,
                port=self.settings.redis_port,
                password=self.settings.redis_password,
                db=self.settings.redis_db,
                decode_responses=False,  # We handle encoding/decoding
                socket_connect_timeout=5,
                socket_timeout=5,
                max_connections=50,
            )

            # Test connection
            self._redis_client.ping()
            logger.info("Connected to Redis")

            # Initialize encryption
            self._init_encryption()

        except redis.RedisError as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise

    def close(self) -> None:
        """Close Redis connection"""
        if self._redis_client:
            self._redis_client.close()
            logger.info("Closed Redis connection")

    def _init_encryption(self) -> None:
        """Initialize Fernet encryption cipher"""
        encryption_key = self.settings.encryption_key

        if not encryption_key:
            # Generate a key for development (NOT for production!)
            logger.warning(
                "No encryption key configured, generating temporary key. "
                "This is NOT secure for production!"
            )
            encryption_key = Fernet.generate_key().decode()

        try:
            # Ensure key is bytes
            if isinstance(encryption_key, str):
                encryption_key = encryption_key.encode()

            self._cipher = Fernet(encryption_key)
            logger.info("Initialized AES-256 encryption")

        except Exception as e:
            raise EncryptionError(
                f"Failed to initialize encryption: {str(e)}",
                details={"key_length": len(encryption_key) if encryption_key else 0},
            ) from e

    def _encrypt(self, data: str) -> bytes:
        """
        Encrypt data using Fernet (AES-256).

        Args:
            data: Data to encrypt

        Returns:
            Encrypted data as bytes
        """
        if not self._cipher:
            raise EncryptionError("Encryption not initialized")

        try:
            return self._cipher.encrypt(data.encode())
        except Exception as e:
            raise EncryptionError(f"Encryption failed: {str(e)}") from e

    def _decrypt(self, encrypted_data: bytes) -> str:
        """
        Decrypt data using Fernet (AES-256).

        Args:
            encrypted_data: Encrypted data

        Returns:
            Decrypted data as string
        """
        if not self._cipher:
            raise EncryptionError("Encryption not initialized")

        try:
            return self._cipher.decrypt(encrypted_data).decode()
        except InvalidToken as e:
            raise EncryptionError("Decryption failed: Invalid token") from e
        except Exception as e:
            raise EncryptionError(f"Decryption failed: {str(e)}") from e

    def _make_key(self, namespace: str, key: str) -> str:
        """
        Create a namespaced cache key.

        Args:
            namespace: Namespace (e.g., "file", "convention")
            key: Key within namespace

        Returns:
            Namespaced key
        """
        return f"bob:{namespace}:{key}"

    def get(self, namespace: str, key: str) -> str | None:
        """
        Get value from cache.

        Args:
            namespace: Cache namespace
            key: Cache key

        Returns:
            Cached value or None if not found
        """
        if not self._redis_client:
            return None

        cache_key = self._make_key(namespace, key)

        try:
            encrypted_data = self._redis_client.get(cache_key)

            if encrypted_data is None:
                logger.debug(f"Cache miss: {cache_key}")
                return None

            # Decrypt and return
            value = self._decrypt(encrypted_data)
            logger.debug(f"Cache hit: {cache_key}")
            return value

        except redis.RedisError as e:
            logger.warning(f"Redis error on get: {e}")
            return None
        except EncryptionError as e:
            logger.warning(f"Decryption error on get: {e}")
            return None

    def set(
        self,
        namespace: str,
        key: str,
        value: str,
        ttl: int | None = None,
    ) -> bool:
        """
        Set value in cache with encryption.

        Args:
            namespace: Cache namespace
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds (None for default)

        Returns:
            True if successful, False otherwise
        """
        if not self._redis_client:
            return False

        cache_key = self._make_key(namespace, key)

        # Use default TTL based on namespace
        if ttl is None:
            if namespace == "file":
                ttl = self._file_ttl
            elif namespace == "convention":
                ttl = self._convention_ttl
            else:
                ttl = self._file_ttl

        try:
            # Encrypt value
            encrypted_data = self._encrypt(value)

            # Store in Redis with TTL
            self._redis_client.setex(cache_key, ttl, encrypted_data)
            logger.debug(f"Cache set: {cache_key} (TTL: {ttl}s)")
            return True

        except redis.RedisError as e:
            logger.warning(f"Redis error on set: {e}")
            return False
        except EncryptionError as e:
            logger.warning(f"Encryption error on set: {e}")
            return False

    def invalidate(self, namespace: str, key: str) -> bool:
        """
        Invalidate (delete) a cache entry.

        Args:
            namespace: Cache namespace
            key: Cache key

        Returns:
            True if deleted, False otherwise
        """
        if not self._redis_client:
            return False

        cache_key = self._make_key(namespace, key)

        try:
            deleted = self._redis_client.delete(cache_key)
            logger.debug(f"Cache invalidated: {cache_key}")
            return deleted > 0

        except redis.RedisError as e:
            logger.warning(f"Redis error on invalidate: {e}")
            return False

    def invalidate_pattern(self, namespace: str, pattern: str) -> int:
        """
        Invalidate all keys matching a pattern.

        Args:
            namespace: Cache namespace
            pattern: Key pattern (supports * wildcard)

        Returns:
            Number of keys deleted
        """
        if not self._redis_client:
            return 0

        cache_pattern = self._make_key(namespace, pattern)

        try:
            # Find all matching keys
            keys = self._redis_client.keys(cache_pattern)

            if not keys:
                return 0

            # Delete all matching keys
            deleted = self._redis_client.delete(*keys)
            logger.info(f"Cache invalidated {deleted} keys matching: {cache_pattern}")
            return deleted

        except redis.RedisError as e:
            logger.warning(f"Redis error on invalidate_pattern: {e}")
            return 0

    def get_json(self, namespace: str, key: str) -> dict[str, Any] | None:
        """
        Get JSON value from cache.

        Args:
            namespace: Cache namespace
            key: Cache key

        Returns:
            Parsed JSON or None if not found
        """
        value = self.get(namespace, key)

        if value is None:
            return None

        try:
            return json.loads(value)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON from cache: {e}")
            return None

    def set_json(
        self,
        namespace: str,
        key: str,
        value: dict[str, Any],
        ttl: int | None = None,
    ) -> bool:
        """
        Set JSON value in cache.

        Args:
            namespace: Cache namespace
            key: Cache key
            value: Dictionary to cache
            ttl: Time-to-live in seconds

        Returns:
            True if successful, False otherwise
        """
        try:
            json_str = json.dumps(value)
            return self.set(namespace, key, json_str, ttl)
        except (TypeError, ValueError) as e:
            logger.warning(f"Failed to serialize JSON for cache: {e}")
            return False

    def get_stats(self) -> dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache stats
        """
        if not self._redis_client:
            return {}

        try:
            info = self._redis_client.info("stats")
            memory_info = self._redis_client.info("memory")

            stats = {
                "total_keys": self._redis_client.dbsize(),
                "hits": info.get("keyspace_hits", 0),
                "misses": info.get("keyspace_misses", 0),
                "evicted_keys": info.get("evicted_keys", 0),
                "expired_keys": info.get("expired_keys", 0),
                "used_memory_human": memory_info.get("used_memory_human", "unknown"),
                "maxmemory_policy": memory_info.get("maxmemory_policy", "unknown"),
            }

            # Calculate hit rate
            total_requests = stats["hits"] + stats["misses"]
            if total_requests > 0:
                stats["hit_rate"] = stats["hits"] / total_requests
            else:
                stats["hit_rate"] = 0.0

            return stats

        except redis.RedisError as e:
            logger.warning(f"Failed to get cache stats: {e}")
            return {}

    def prewarm(self, repo_id: str, files: dict[str, str]) -> int:
        """
        Pre-warm cache with file contents.

        Args:
            repo_id: Repository ID
            files: Dictionary of file_path -> content

        Returns:
            Number of files cached
        """
        cached_count = 0

        for file_path, content in files.items():
            key = f"{repo_id}:{file_path}"
            if self.set("file", key, content):
                cached_count += 1

        logger.info(f"Pre-warmed cache with {cached_count} files for repo {repo_id}")
        return cached_count

    def flush_namespace(self, namespace: str) -> int:
        """
        Flush all keys in a namespace.

        Args:
            namespace: Namespace to flush

        Returns:
            Number of keys deleted
        """
        return self.invalidate_pattern(namespace, "*")

    def flush_all(self) -> bool:
        """
        Flush entire cache (use with caution!).

        Returns:
            True if successful
        """
        if not self._redis_client:
            return False

        try:
            self._redis_client.flushdb()
            logger.warning("Flushed entire cache database")
            return True

        except redis.RedisError as e:
            logger.error(f"Failed to flush cache: {e}")
            return False


# Made with Bob
