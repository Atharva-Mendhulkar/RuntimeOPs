"""
IBM Bob - Weaviate Vector Store
Manages vector embeddings in Weaviate for semantic code search
"""

import logging
from typing import Any
from uuid import UUID

import weaviate
from weaviate.classes.config import Configure, DataType, Property, VectorDistances
from weaviate.classes.query import Filter, MetadataQuery
from weaviate.exceptions import WeaviateBaseError

from bob.config import get_settings
from bob.exceptions import VectorStoreConnectionError, VectorStoreError
from bob.semantic.embedder import Embedding

logger = logging.getLogger(__name__)


class VectorStore:
    """
    Manages vector embeddings in Weaviate.

    Responsibilities:
    - Create/update CodeUnit schema
    - Batch upsert for code unit objects
    - Namespace isolation by repo_id
    - Nearest-neighbor search with metadata filtering
    - Vector invalidation on file changes
    - Handle connection errors gracefully
    """

    def __init__(self) -> None:
        """Initialize the vector store"""
        self.settings = get_settings()
        self._client = None
        self._collection_name = "CodeUnit"
        self._batch_size = 100

    def __enter__(self) -> "VectorStore":
        """Context manager entry"""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit"""
        self.close()

    def connect(self) -> None:
        """Connect to Weaviate"""
        try:
            # Connect to Weaviate
            if self.settings.weaviate_api_key:
                self._client = weaviate.connect_to_custom(
                    http_host=self.settings.weaviate_url.replace("http://", "").replace(
                        "https://", ""
                    ),
                    http_port=8080,
                    http_secure=False,
                    grpc_host=self.settings.weaviate_url.replace("http://", "").replace(
                        "https://", ""
                    ),
                    grpc_port=50051,
                    grpc_secure=False,
                    auth_credentials=weaviate.auth.AuthApiKey(self.settings.weaviate_api_key),
                )
            else:
                self._client = weaviate.connect_to_local(
                    host=self.settings.weaviate_url.replace("http://", "").replace("https://", ""),
                    port=8080,
                    grpc_port=50051,
                )

            # Verify connection
            if not self._client.is_ready():
                raise VectorStoreConnectionError("Weaviate is not ready")

            logger.info("Connected to Weaviate")

            # Create schema if it doesn't exist
            self._create_schema()

        except Exception as e:
            raise VectorStoreConnectionError(
                f"Failed to connect to Weaviate: {str(e)}",
                details={"url": self.settings.weaviate_url},
            ) from e

    def close(self) -> None:
        """Close Weaviate connection"""
        if self._client:
            self._client.close()
            logger.info("Closed Weaviate connection")

    def _create_schema(self) -> None:
        """Create Weaviate collections if they don't exist"""
        assert self._client is not None, "Client not connected"
        if self._client.collections.exists(self._collection_name):
            logger.info(f"Collection {self._collection_name} already exists")
            return

        # Create collection with schema
        try:
            self._client.collections.create(
                name=self._collection_name,
                description="Code units (functions, classes, methods) with semantic embeddings",
                vectorizer_config=Configure.Vectorizer.none(),  # We provide our own vectors
                vector_index_config=Configure.VectorIndex.hnsw(
                    distance_metric=VectorDistances.COSINE,
                    ef=128,
                    ef_construction=256,
                    max_connections=64,
                ),
                properties=[
                    Property(
                        name="repo_id",
                        data_type=DataType.TEXT,
                        description="Repository UUID",
                        index_filterable=True,
                        index_searchable=False,
                    ),
                    Property(
                        name="file_path",
                        data_type=DataType.TEXT,
                        description="File path relative to repository root",
                        index_filterable=True,
                        index_searchable=True,
                    ),
                    Property(
                        name="symbol_name",
                        data_type=DataType.TEXT,
                        description="Symbol name (function, class, etc.)",
                        index_filterable=True,
                        index_searchable=True,
                    ),
                    Property(
                        name="symbol_type",
                        data_type=DataType.TEXT,
                        description="Symbol type (function, class, method, etc.)",
                        index_filterable=True,
                        index_searchable=False,
                    ),
                    Property(
                        name="content",
                        data_type=DataType.TEXT,
                        description="Code content",
                        index_filterable=False,
                        index_searchable=True,
                    ),
                    Property(
                        name="start_line",
                        data_type=DataType.INT,
                        description="Start line number",
                        index_filterable=True,
                        index_searchable=False,
                    ),
                    Property(
                        name="end_line",
                        data_type=DataType.INT,
                        description="End line number",
                        index_filterable=True,
                        index_searchable=False,
                    ),
                    Property(
                        name="language",
                        data_type=DataType.TEXT,
                        description="Programming language",
                        index_filterable=True,
                        index_searchable=False,
                    ),
                    Property(
                        name="embedding_model",
                        data_type=DataType.TEXT,
                        description="Embedding model used",
                        index_filterable=False,
                        index_searchable=False,
                    ),
                    Property(
                        name="indexed_at",
                        data_type=DataType.DATE,
                        description="Timestamp when indexed",
                        index_filterable=True,
                        index_searchable=False,
                    ),
                ],
            )

            logger.info(f"Created collection {self._collection_name}")

        except WeaviateBaseError as e:
            logger.warning(f"Failed to create schema: {e}")

    def upsert_embeddings(
        self,
        repo_id: UUID,
        embeddings: list[Embedding],
        language: str,
    ) -> int:
        """
        Upsert embeddings in batches.

        Args:
            repo_id: Repository UUID
            embeddings: List of embeddings to upsert
            language: Programming language

        Returns:
            Number of embeddings upserted
        """
        if not embeddings:
            return 0

        assert self._client is not None, "Client not connected"
        collection = self._client.collections.get(self._collection_name)

        # Batch upsert
        total_upserted = 0

        with collection.batch.dynamic() as batch:
            for embedding in embeddings:
                # Create unique ID based on repo, file, symbol, and line
                object_id = f"{repo_id}:{embedding.chunk.file_path}:{embedding.chunk.symbol_name}:{embedding.chunk.start_line}"

                properties = {
                    "repo_id": str(repo_id),
                    "file_path": embedding.chunk.file_path,
                    "symbol_name": embedding.chunk.symbol_name,
                    "symbol_type": embedding.chunk.symbol_type,
                    "content": embedding.chunk.content,
                    "start_line": embedding.chunk.start_line,
                    "end_line": embedding.chunk.end_line,
                    "language": language,
                    "embedding_model": embedding.model,
                    "indexed_at": embedding.timestamp,
                }

                batch.add_object(
                    properties=properties,
                    vector=embedding.vector,
                    uuid=weaviate.util.generate_uuid5(object_id),
                )
                total_upserted += 1

        logger.info(f"Upserted {total_upserted} embeddings for repo {repo_id}")
        return total_upserted

    def search(
        self,
        query_vector: list[float],
        repo_id: UUID | None = None,
        file_path: str | None = None,
        symbol_type: str | None = None,
        language: str | None = None,
        limit: int = 10,
        offset: int = 0,
        min_certainty: float = 0.7,
    ) -> list[dict[str, Any]]:
        """
        Perform nearest-neighbor search with optional filters.

        Args:
            query_vector: Query embedding vector
            repo_id: Optional repository filter
            file_path: Optional file path filter
            symbol_type: Optional symbol type filter
            language: Optional language filter
            limit: Maximum number of results
            min_certainty: Minimum certainty score (0.0-1.0)

        Returns:
            List of search results with metadata
        """
        collection = self._client.collections.get(self._collection_name)

        # Build filters
        filters = []
        if repo_id:
            filters.append(Filter.by_property("repo_id").equal(str(repo_id)))
        if file_path:
            filters.append(Filter.by_property("file_path").equal(file_path))
        if symbol_type:
            filters.append(Filter.by_property("symbol_type").equal(symbol_type))
        if language:
            filters.append(Filter.by_property("language").equal(language))

        # Combine filters with AND
        combined_filter = None
        if filters:
            combined_filter = filters[0]
            for f in filters[1:]:
                combined_filter = combined_filter & f

        # Perform search
        try:
            # Weaviate v4 Python client passes offset to GraphQL
            response = collection.query.near_vector(
                near_vector=query_vector,
                limit=limit,
                offset=offset,
                filters=combined_filter,
                return_metadata=MetadataQuery(certainty=True, distance=True),
            )

            results = []
            for obj in response.objects:
                # Filter by certainty
                if obj.metadata.certainty and obj.metadata.certainty < min_certainty:
                    continue

                results.append(
                    {
                        "repo_id": obj.properties.get("repo_id"),
                        "file_path": obj.properties.get("file_path"),
                        "symbol_name": obj.properties.get("symbol_name"),
                        "symbol_type": obj.properties.get("symbol_type"),
                        "content": obj.properties.get("content"),
                        "start_line": obj.properties.get("start_line"),
                        "end_line": obj.properties.get("end_line"),
                        "language": obj.properties.get("language"),
                        "certainty": obj.metadata.certainty,
                        "distance": obj.metadata.distance,
                    }
                )

            logger.info(f"Found {len(results)} results for semantic search")
            return results

        except WeaviateBaseError as e:
            raise VectorStoreError(
                f"Search failed: {str(e)}",
                details={"repo_id": str(repo_id) if repo_id else None},
            ) from e

    def search_by_text(
        self,
        query_text: str,
        repo_id: UUID | None = None,
        file_path: str | None = None,
        symbol_type: str | None = None,
        language: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Perform hybrid search (BM25 + semantic).

        Args:
            query_text: Query text
            repo_id: Optional repository filter
            file_path: Optional file path filter
            symbol_type: Optional symbol type filter
            language: Optional language filter
            limit: Maximum number of results

        Returns:
            List of search results with metadata
        """
        collection = self._client.collections.get(self._collection_name)

        # Build filters
        filters = []
        if repo_id:
            filters.append(Filter.by_property("repo_id").equal(str(repo_id)))
        if file_path:
            filters.append(Filter.by_property("file_path").equal(file_path))
        if symbol_type:
            filters.append(Filter.by_property("symbol_type").equal(symbol_type))
        if language:
            filters.append(Filter.by_property("language").equal(language))

        # Combine filters
        combined_filter = None
        if filters:
            combined_filter = filters[0]
            for f in filters[1:]:
                combined_filter = combined_filter & f

        # Perform hybrid search
        try:
            response = collection.query.hybrid(
                query=query_text,
                limit=limit,
                filters=combined_filter,
                return_metadata=MetadataQuery(score=True),
            )

            results = []
            for obj in response.objects:
                results.append(
                    {
                        "repo_id": obj.properties.get("repo_id"),
                        "file_path": obj.properties.get("file_path"),
                        "symbol_name": obj.properties.get("symbol_name"),
                        "symbol_type": obj.properties.get("symbol_type"),
                        "content": obj.properties.get("content"),
                        "start_line": obj.properties.get("start_line"),
                        "end_line": obj.properties.get("end_line"),
                        "language": obj.properties.get("language"),
                        "score": obj.metadata.score,
                    }
                )

            logger.info(f"Found {len(results)} results for hybrid search")
            return results

        except WeaviateBaseError as e:
            raise VectorStoreError(
                f"Hybrid search failed: {str(e)}",
                details={"query": query_text},
            ) from e

    def invalidate_file(self, repo_id: UUID, file_path: str) -> int:
        """
        Invalidate (delete) all embeddings for a file.

        Args:
            repo_id: Repository UUID
            file_path: File path

        Returns:
            Number of embeddings deleted
        """
        collection = self._client.collections.get(self._collection_name)

        try:
            # Delete all objects matching repo_id and file_path
            result = collection.data.delete_many(
                where=Filter.by_property("repo_id").equal(str(repo_id))
                & Filter.by_property("file_path").equal(file_path)
            )

            deleted_count = result.successful if hasattr(result, "successful") else 0
            logger.info(f"Invalidated {deleted_count} embeddings for {file_path}")
            return deleted_count

        except WeaviateBaseError as e:
            raise VectorStoreError(
                f"Failed to invalidate file: {str(e)}",
                details={"repo_id": str(repo_id), "file_path": file_path},
            ) from e

    def invalidate_repository(self, repo_id: UUID) -> int:
        """
        Invalidate (delete) all embeddings for a repository.

        Args:
            repo_id: Repository UUID

        Returns:
            Number of embeddings deleted
        """
        collection = self._client.collections.get(self._collection_name)

        try:
            # Delete all objects matching repo_id
            result = collection.data.delete_many(
                where=Filter.by_property("repo_id").equal(str(repo_id))
            )

            deleted_count = result.successful if hasattr(result, "successful") else 0
            logger.info(f"Invalidated {deleted_count} embeddings for repo {repo_id}")
            return deleted_count

        except WeaviateBaseError as e:
            raise VectorStoreError(
                f"Failed to invalidate repository: {str(e)}",
                details={"repo_id": str(repo_id)},
            ) from e

    def get_stats(self, repo_id: UUID | None = None) -> dict[str, Any]:
        """
        Get statistics about stored embeddings.

        Args:
            repo_id: Optional repository filter

        Returns:
            Dictionary with statistics
        """
        collection = self._client.collections.get(self._collection_name)

        try:
            # Get total count
            if repo_id:
                response = collection.aggregate.over_all(
                    filters=Filter.by_property("repo_id").equal(str(repo_id)),
                    total_count=True,
                )
            else:
                response = collection.aggregate.over_all(total_count=True)

            stats = {
                "total_embeddings": response.total_count if response.total_count else 0,
                "repo_id": str(repo_id) if repo_id else "all",
            }

            logger.info(f"Vector store stats: {stats}")
            return stats

        except WeaviateBaseError as e:
            logger.warning(f"Failed to get stats: {e}")
            return {"total_embeddings": 0, "repo_id": str(repo_id) if repo_id else "all"}


# Made with Bob
