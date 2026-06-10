"""
IBM Bob - Result Assembler & Confidence Scoring
Implements 4-stage reasoning pipeline for query results
"""

import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from bob.config import get_settings
from bob.graph.query import GraphQuery

logger = logging.getLogger(__name__)


@dataclass
class Evidence:
    """Evidence reference for a result"""

    file_path: str
    line_range: tuple[int, int]
    commit_sha: str | None = None
    author: str | None = None
    last_modified: str | None = None


@dataclass
class AssembledResult:
    """Assembled result with confidence score and evidence"""

    file_path: str
    symbol_name: str
    symbol_type: str
    start_line: int
    end_line: int
    content: str
    language: str
    confidence: float
    evidence: Evidence
    metadata: dict[str, Any]


class ResultAssembler:
    """
    Assembles and scores query results using 4-stage reasoning pipeline.

    Pipeline stages:
    1. Recall: Vector nearest-neighbor search (Weaviate)
    2. Re-rank: Optional lightweight LLM re-ranking (8B model)
    3. Evidence Assembly: Annotate with file metadata, dependency count, ACS
    4. Confidence Scoring: Weighted combination of signals

    Confidence scoring weights:
    - Vector similarity: 0.50
    - Re-rank score: 0.35 (if re-ranking enabled)
    - Graph centrality: 0.15
    """

    def __init__(
        self,
        enable_reranking: bool = False,
        max_tokens: int = 4096,
    ) -> None:
        """
        Initialize the result assembler.

        Args:
            enable_reranking: Whether to enable LLM re-ranking
            max_tokens: Maximum tokens per response
        """
        self.settings = get_settings()
        self.enable_reranking = enable_reranking
        self.max_tokens = max_tokens

        # Confidence scoring weights
        self.weights = {
            "vector_similarity": 0.50,
            "rerank_score": 0.35 if enable_reranking else 0.0,
            "graph_centrality": 0.15 if not enable_reranking else 0.50,
        }

    async def assemble_search_results(
        self,
        repo_id: UUID,
        query: str,
        raw_results: list[dict[str, Any]],
        include_graph_metadata: bool = True,
    ) -> list[AssembledResult]:
        """
        Assemble search results through 4-stage pipeline.

        Args:
            repo_id: Repository UUID
            query: Original query
            raw_results: Raw results from vector store
            include_graph_metadata: Whether to include graph metadata

        Returns:
            List of assembled results with confidence scores
        """
        if not raw_results:
            return []

        # Stage 1: Recall (already done - raw_results from Weaviate)
        logger.debug(f"Stage 1 (Recall): {len(raw_results)} results from vector store")

        # Stage 2: Re-rank (optional)
        if self.enable_reranking:
            raw_results = await self._rerank_results(query, raw_results)
            logger.debug(f"Stage 2 (Re-rank): Re-ranked {len(raw_results)} results")
        else:
            logger.debug("Stage 2 (Re-rank): Skipped (disabled)")

        # Stage 3: Evidence Assembly
        assembled_results = []

        with GraphQuery() as graph_query:
            for result in raw_results:
                try:
                    # Get file metadata from graph
                    file_metadata = {}
                    if include_graph_metadata:
                        file_metadata = graph_query.get_file_metrics(
                            repo_id=repo_id,
                            file_path=result["file_path"],
                        )

                    # Get git blame for evidence
                    git_blame = graph_query.get_git_blame(
                        repo_id=repo_id,
                        file_path=result["file_path"],
                        line_range=(result["start_line"], result["end_line"]),
                    )

                    # Create evidence
                    evidence = Evidence(
                        file_path=result["file_path"],
                        line_range=(result["start_line"], result["end_line"]),
                        commit_sha=(
                            git_blame.commits[0]["commit_hash"] if git_blame.commits else None
                        ),
                        author=git_blame.commits[0]["author"] if git_blame.commits else None,
                        last_modified=(
                            git_blame.commits[0]["commit_date"] if git_blame.commits else None
                        ),
                    )

                    # Assemble metadata
                    metadata = {
                        "vector_similarity": result.get("certainty", 0.0),
                        "rerank_score": result.get("rerank_score", 0.0),
                        "graph_centrality": self._calculate_centrality(file_metadata),
                        "dependency_count": file_metadata.get("imports_count", 0)
                        + file_metadata.get("importers_count", 0),
                        "acs_score": file_metadata.get("acs_score"),
                        "total_lines": file_metadata.get("total_lines", 0),
                    }

                    # Stage 4: Confidence Scoring
                    confidence = self._calculate_confidence(metadata)

                    assembled_result = AssembledResult(
                        file_path=result["file_path"],
                        symbol_name=result["symbol_name"],
                        symbol_type=result["symbol_type"],
                        start_line=result["start_line"],
                        end_line=result["end_line"],
                        content=result["content"],
                        language=result["language"],
                        confidence=confidence,
                        evidence=evidence,
                        metadata=metadata,
                    )

                    assembled_results.append(assembled_result)

                except Exception as e:
                    logger.warning(f"Failed to assemble result for {result.get('file_path')}: {e}")
                    continue

        logger.debug(f"Stage 3 (Evidence Assembly): Assembled {len(assembled_results)} results")
        logger.debug(f"Stage 4 (Confidence Scoring): Scored {len(assembled_results)} results")

        # Sort by confidence (descending)
        assembled_results.sort(key=lambda r: r.confidence, reverse=True)

        # Trim to token budget
        trimmed_results = self._trim_to_token_budget(assembled_results)
        logger.debug(f"Trimmed to {len(trimmed_results)} results within token budget")

        return trimmed_results

    async def _rerank_results(
        self,
        query: str,
        results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Re-rank results using lightweight LLM (8B model).

        Args:
            query: Original query
            results: Results to re-rank

        Returns:
            Re-ranked results with rerank_score added
        """
        # TODO: Implement LLM re-ranking
        # For now, just pass through with default scores
        logger.warning("LLM re-ranking not yet implemented, using default scores")

        for result in results:
            # Placeholder: use vector similarity as rerank score
            result["rerank_score"] = result.get("certainty", 0.5)

        return results

    def _calculate_centrality(self, file_metadata: dict[str, Any]) -> float:
        """
        Calculate graph centrality score for a file.

        Args:
            file_metadata: File metadata from graph

        Returns:
            Centrality score (0.0-1.0)
        """
        if not file_metadata:
            return 0.0

        # Use fan-in + fan-out as proxy for centrality
        fan_in = file_metadata.get("fan_in", 0)
        fan_out = file_metadata.get("fan_out", 0)
        total_connections = fan_in + fan_out

        # Normalize to 0-1 range (assume max 50 connections)
        centrality = min(total_connections / 50.0, 1.0)

        return centrality

    def _calculate_confidence(self, metadata: dict[str, Any]) -> float:
        """
        Calculate confidence score using weighted combination.

        Weights:
        - Vector similarity: 0.50
        - Re-rank score: 0.35 (if enabled)
        - Graph centrality: 0.15 (or 0.50 if re-ranking disabled)

        Args:
            metadata: Result metadata

        Returns:
            Confidence score (0.0-1.0)
        """
        confidence = 0.0

        # Vector similarity component
        vector_sim = metadata.get("vector_similarity", 0.0)
        confidence += vector_sim * self.weights["vector_similarity"]

        # Re-rank score component (if enabled)
        if self.enable_reranking:
            rerank_score = metadata.get("rerank_score", 0.0)
            confidence += rerank_score * self.weights["rerank_score"]

        # Graph centrality component
        centrality = metadata.get("graph_centrality", 0.0)
        confidence += centrality * self.weights["graph_centrality"]

        # Ensure confidence is in [0, 1]
        confidence = max(0.0, min(1.0, confidence))

        return confidence

    def _trim_to_token_budget(
        self,
        results: list[AssembledResult],
    ) -> list[AssembledResult]:
        """
        Trim results to fit within token budget.

        Args:
            results: Assembled results

        Returns:
            Trimmed results
        """
        # Rough estimate: 4 characters per token
        chars_per_token = 4
        max_chars = self.max_tokens * chars_per_token

        trimmed_results = []
        total_chars = 0

        for result in results:
            # Estimate tokens for this result
            result_chars = len(result.content) + len(result.file_path) + 200  # +200 for metadata

            if total_chars + result_chars > max_chars:
                logger.debug(
                    f"Token budget exceeded, stopping at {len(trimmed_results)} results "
                    f"({total_chars} chars / {total_chars // chars_per_token} tokens)"
                )
                break

            trimmed_results.append(result)
            total_chars += result_chars

        return trimmed_results

    def enrich_with_dependencies(
        self,
        repo_id: UUID,
        results: list[AssembledResult],
        max_hops: int = 2,
    ) -> list[AssembledResult]:
        """
        Enrich results with dependency information.

        Args:
            repo_id: Repository UUID
            results: Assembled results
            max_hops: Maximum dependency hops

        Returns:
            Enriched results
        """
        with GraphQuery() as graph_query:
            for result in results:
                try:
                    # Get dependencies
                    deps = graph_query.get_dependencies(
                        repo_id=repo_id,
                        file_path=result.file_path,
                        direction="both",
                        max_hops=max_hops,
                    )

                    # Add to metadata
                    result.metadata["upstream_dependencies"] = deps["upstream"][:5]  # Top 5
                    result.metadata["downstream_dependencies"] = deps["downstream"][:5]  # Top 5
                    result.metadata["total_dependencies"] = len(deps["upstream"]) + len(
                        deps["downstream"]
                    )

                except Exception as e:
                    logger.warning(f"Failed to enrich dependencies for {result.file_path}: {e}")
                    continue

        return results

    def filter_by_confidence(
        self,
        results: list[AssembledResult],
        min_confidence: float = 0.5,
    ) -> list[AssembledResult]:
        """
        Filter results by minimum confidence threshold.

        Args:
            results: Assembled results
            min_confidence: Minimum confidence threshold

        Returns:
            Filtered results
        """
        filtered = [r for r in results if r.confidence >= min_confidence]
        logger.debug(
            f"Filtered {len(results)} results to {len(filtered)} "
            f"with min_confidence={min_confidence}"
        )
        return filtered

    def deduplicate_results(
        self,
        results: list[AssembledResult],
    ) -> list[AssembledResult]:
        """
        Remove duplicate results (same file + symbol).

        Args:
            results: Assembled results

        Returns:
            Deduplicated results
        """
        seen = set()
        deduplicated = []

        for result in results:
            key = (result.file_path, result.symbol_name, result.start_line)
            if key not in seen:
                seen.add(key)
                deduplicated.append(result)

        if len(deduplicated) < len(results):
            logger.debug(f"Deduplicated {len(results)} results to {len(deduplicated)}")

        return deduplicated

    def format_for_response(
        self,
        results: list[AssembledResult],
    ) -> list[dict[str, Any]]:
        """
        Format assembled results for API response.

        Args:
            results: Assembled results

        Returns:
            List of result dictionaries
        """
        formatted = []

        for result in results:
            formatted.append(
                {
                    "file_path": result.file_path,
                    "symbol_name": result.symbol_name,
                    "symbol_type": result.symbol_type,
                    "start_line": result.start_line,
                    "end_line": result.end_line,
                    "content": result.content,
                    "language": result.language,
                    "confidence": round(result.confidence, 3),
                    "evidence": {
                        "commit_sha": result.evidence.commit_sha,
                        "author": result.evidence.author,
                        "last_modified": result.evidence.last_modified,
                    },
                    "metadata": {
                        k: v
                        for k, v in result.metadata.items()
                        if k in ["dependency_count", "acs_score", "total_lines"]
                    },
                }
            )

        return formatted


# Made with Bob
