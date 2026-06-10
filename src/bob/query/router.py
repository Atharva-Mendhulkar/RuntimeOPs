"""
IBM Bob - Query Router
Classifies and routes queries to appropriate backend stores
"""

import logging
import re
from enum import Enum
from typing import Any
from uuid import UUID

from bob.config import get_settings

logger = logging.getLogger(__name__)


class QueryType(Enum):
    """Query type classification"""

    SEMANTIC = "semantic"  # Natural language queries → Weaviate
    GRAPH = "graph"  # Dependency traversal, blast radius → Neo4j
    FILE = "file"  # File content retrieval → Redis cache → Git
    HYBRID = "hybrid"  # Semantic search + graph enrichment → both stores


class QueryRouter:
    """
    Routes queries to appropriate backend based on query type.

    Responsibilities:
    - Classify query types (semantic, graph, file, hybrid)
    - Route to appropriate backend (Weaviate, Neo4j, Redis, Git)
    - Apply query optimization logic
    - Handle query parameter validation
    """

    def __init__(self) -> None:
        """Initialize the query router"""
        self.settings = get_settings()

        # Patterns for query classification
        self._semantic_patterns = [
            r"find.*function",
            r"search.*for",
            r"where.*is",
            r"show.*me",
            r"locate",
            r"authentication",
            r"database.*connection",
            r"error.*handling",
            r"logging",
            r"validation",
        ]

        self._graph_patterns = [
            r"depend",
            r"import",
            r"call.*chain",
            r"upstream",
            r"downstream",
            r"blast.*radius",
            r"impact",
            r"affect",
            r"service.*topology",
        ]

    def classify_query(self, query: str, context: dict[str, Any] | None = None) -> QueryType:
        """
        Classify query type based on query text and context.

        Args:
            query: Query text
            context: Optional context (e.g., endpoint, parameters)

        Returns:
            QueryType enum value
        """
        query_lower = query.lower()

        # Check context first (explicit endpoint routing)
        if context:
            endpoint = context.get("endpoint", "")

            if "dependency" in endpoint or "blast-radius" in endpoint:
                return QueryType.GRAPH
            elif "file" in endpoint:
                return QueryType.FILE
            elif "search" in endpoint:
                # Check if hybrid search is requested
                if context.get("include_graph", False):
                    return QueryType.HYBRID
                return QueryType.SEMANTIC

        # Pattern-based classification
        graph_score = sum(1 for pattern in self._graph_patterns if re.search(pattern, query_lower))

        semantic_score = sum(
            1 for pattern in self._semantic_patterns if re.search(pattern, query_lower)
        )

        # Decide based on scores
        if graph_score > semantic_score:
            return QueryType.GRAPH
        elif semantic_score > 0:
            return QueryType.SEMANTIC
        elif graph_score > 0:
            return QueryType.GRAPH
        else:
            # Default to semantic for natural language queries
            return QueryType.SEMANTIC

    def route_search_query(
        self,
        repo_id: UUID,
        query: str,
        k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Route semantic search query.

        Args:
            repo_id: Repository UUID
            query: Search query
            k: Number of results
            filters: Optional filters

        Returns:
            Routing decision with backend and parameters
        """
        query_type = self.classify_query(query, {"endpoint": "search"})

        routing = {
            "query_type": query_type.value,
            "backend": "weaviate",
            "params": {
                "repo_id": repo_id,
                "query": query,
                "k": k,
                "filters": filters or {},
            },
            "optimization": self._get_search_optimization(query, k),
        }

        logger.debug(f"Routed search query to {routing['backend']}: {query[:50]}...")
        return routing

    def route_graph_query(
        self,
        repo_id: UUID,
        operation: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Route graph query.

        Args:
            repo_id: Repository UUID
            operation: Graph operation (dependencies, blast_radius, etc.)
            params: Operation parameters

        Returns:
            Routing decision with backend and parameters
        """
        routing = {
            "query_type": QueryType.GRAPH.value,
            "backend": "neo4j",
            "operation": operation,
            "params": {
                "repo_id": repo_id,
                **params,
            },
            "optimization": self._get_graph_optimization(operation, params),
        }

        logger.debug(f"Routed graph query to {routing['backend']}: {operation}")
        return routing

    def route_file_query(
        self,
        repo_id: UUID,
        file_path: str,
    ) -> dict[str, Any]:
        """
        Route file content query.

        Args:
            repo_id: Repository UUID
            file_path: File path

        Returns:
            Routing decision with backend and parameters
        """
        routing = {
            "query_type": QueryType.FILE.value,
            "backend": "redis",  # Try cache first
            "fallback": "git",  # Fallback to Git if cache miss
            "params": {
                "repo_id": repo_id,
                "file_path": file_path,
            },
            "optimization": {
                "cache_first": True,
                "cache_ttl": self.settings.file_cache_ttl_seconds,
            },
        }

        logger.debug(f"Routed file query to {routing['backend']}: {file_path}")
        return routing

    def route_hybrid_query(
        self,
        repo_id: UUID,
        query: str,
        k: int = 10,
        graph_hops: int = 3,
    ) -> dict[str, Any]:
        """
        Route hybrid query (semantic + graph).

        Args:
            repo_id: Repository UUID
            query: Search query
            k: Number of semantic results
            graph_hops: Graph traversal hops

        Returns:
            Routing decision with multiple backends
        """
        routing = {
            "query_type": QueryType.HYBRID.value,
            "backends": ["weaviate", "neo4j"],
            "stages": [
                {
                    "stage": "semantic_search",
                    "backend": "weaviate",
                    "params": {
                        "repo_id": repo_id,
                        "query": query,
                        "k": k,
                    },
                },
                {
                    "stage": "graph_enrichment",
                    "backend": "neo4j",
                    "params": {
                        "repo_id": repo_id,
                        "hops": graph_hops,
                    },
                },
            ],
            "optimization": {
                "parallel_execution": False,  # Sequential for hybrid
                "cache_intermediate": True,
            },
        }

        logger.debug(f"Routed hybrid query to {routing['backends']}: {query[:50]}...")
        return routing

    def _get_search_optimization(self, query: str, k: int) -> dict[str, Any]:
        """
        Get optimization hints for semantic search.

        Args:
            query: Search query
            k: Number of results

        Returns:
            Optimization hints
        """
        optimization = {
            "use_cache": True,
            "cache_ttl": self.settings.query_result_cache_ttl_seconds,
            "min_certainty": 0.7,  # Filter low-confidence results
        }

        # Adjust based on query characteristics
        if len(query.split()) > 10:
            # Long queries - increase result count for better recall
            optimization["k_multiplier"] = 1.5

        if k > 20:
            # Large result sets - enable pagination
            optimization["enable_pagination"] = True

        return optimization

    def _get_graph_optimization(
        self,
        operation: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Get optimization hints for graph queries.

        Args:
            operation: Graph operation
            params: Operation parameters

        Returns:
            Optimization hints
        """
        optimization = {
            "use_cache": True,
            "cache_ttl": self.settings.query_result_cache_ttl_seconds,
            "timeout": self.settings.query_timeout_seconds,
        }

        # Adjust based on operation
        if operation == "blast_radius":
            max_hops = params.get("max_hops", 5)
            if max_hops > 5:
                # Deep traversal - increase timeout
                optimization["timeout"] = self.settings.query_timeout_seconds * 2
                optimization["use_cache"] = True  # Cache is critical for deep traversals

        elif operation == "dependencies":
            direction = params.get("direction", "both")
            if direction == "both":
                # Bidirectional - can parallelize
                optimization["parallel_execution"] = True

        return optimization

    def should_use_cache(self, query_type: QueryType, params: dict[str, Any]) -> bool:
        """
        Determine if query should use cache.

        Args:
            query_type: Query type
            params: Query parameters

        Returns:
            True if cache should be used
        """
        # Always cache file queries
        if query_type == QueryType.FILE:
            return True

        # Cache graph queries for expensive operations
        if query_type == QueryType.GRAPH:
            operation = params.get("operation", "")
            if operation in ("blast_radius", "service_topology", "call_chain"):
                return True

        # Cache semantic queries with common patterns
        if query_type == QueryType.SEMANTIC:
            query = params.get("query", "")
            # Cache if query is longer than 5 words (likely specific)
            if len(query.split()) >= 5:
                return True

        return False

    def estimate_query_cost(
        self,
        query_type: QueryType,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Estimate query execution cost.

        Args:
            query_type: Query type
            params: Query parameters

        Returns:
            Cost estimate with time and resource metrics
        """
        cost = {
            "estimated_time_ms": 0,
            "complexity": "low",
            "resource_usage": "low",
        }

        if query_type == QueryType.SEMANTIC:
            k = params.get("k", 10)
            cost["estimated_time_ms"] = 100 + (k * 10)  # Base + per-result
            cost["complexity"] = "low" if k <= 20 else "medium"

        elif query_type == QueryType.GRAPH:
            operation = params.get("operation", "")
            max_hops = params.get("max_hops", 3)

            if operation == "blast_radius":
                # Exponential with hops
                cost["estimated_time_ms"] = 200 * (2**max_hops)
                cost["complexity"] = "high" if max_hops > 5 else "medium"
                cost["resource_usage"] = "high" if max_hops > 5 else "medium"
            else:
                cost["estimated_time_ms"] = 150 + (max_hops * 50)
                cost["complexity"] = "medium"

        elif query_type == QueryType.FILE:
            cost["estimated_time_ms"] = 50  # Fast cache lookup
            cost["complexity"] = "low"

        elif query_type == QueryType.HYBRID:
            # Sum of semantic + graph
            cost["estimated_time_ms"] = 500
            cost["complexity"] = "high"
            cost["resource_usage"] = "high"

        return cost


# Made with Bob
