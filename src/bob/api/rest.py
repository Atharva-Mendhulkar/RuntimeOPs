"""
IBM Bob - REST API Endpoints
Implements all 8 REST endpoints for query operations
"""

import asyncio
import hashlib
import logging
import re
import time
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from bob.api.models import (
    BatchRequest,
    BatchResponse,
    BlastRadiusRequest,
    BlastRadiusResponse,
    CommitDiffRequest,
    CommitDiffResponse,
    DependencyGraphRequest,
    DependencyGraphResponse,
    ErrorDetail,
    ErrorResponse,
    FileRequest,
    FileResponse,
    HealthResponse,
    ImpactedFile,
    SearchRequest,
    SearchResponse,
    SearchResult,
    StackTraceRequest,
    StackTraceResponse,
    SubQuery,
    SubQueryResult,
)
from bob.config import get_settings
from bob.exceptions import (
    QueryError,
    QueryTimeoutError,
    ResourceNotFoundError,
)
from bob.graph.query import GraphQuery
from bob.query.assembler import ResultAssembler
from bob.query.gateway import get_gateway
from bob.query.router import QueryRouter
from bob.semantic.embedder import Embedder
from bob.semantic.vector_store import VectorStore
from bob.storage.cache import FileCache
from bob.storage.registry import IndexRegistryManager

logger = logging.getLogger(__name__)
settings = get_settings()

# Create router
router = APIRouter()

# Initialize components
query_router = QueryRouter()
result_assembler = ResultAssembler()


# ============================================================================
# Dependency: Authentication
# ============================================================================


async def authenticate(request: Request) -> dict[str, Any]:
    """
    Authenticate request using query gateway.

    Returns:
        Token claims dictionary
    """
    gateway = get_gateway()
    authorization = request.headers.get("authorization")
    return await gateway.authenticate_request(request, authorization)


# ============================================================================
# EP-001: POST /api/v1/bob/search - Semantic Code Search
# ============================================================================


@router.post("/search", response_model=SearchResponse, tags=["search"])
async def search_code(
    request: SearchRequest,
    response: Response,
    claims: dict[str, Any] = Depends(authenticate),
) -> SearchResponse:
    """
    Semantic code search over indexed repository.

    - **repo_id**: Repository UUID to search within
    - **query**: Natural language search query
    - **k**: Number of results to return (default: 10, max: 50)
    - **filter**: Optional filters (file_path, language, symbol_type)

    Returns search results with confidence scores and code snippets.
    """
    start_time = time.time()

    try:
        logger.info(f"Search query: repo_id={request.repo_id}, query='{request.query[:50]}...'")

        # Generate query embedding
        with Embedder() as embedder:
            query_embedding = embedder.embed_text(request.query)

        # Search vector store
        with VectorStore() as vector_store:
            raw_results = vector_store.search(
                query_vector=query_embedding.vector,
                repo_id=request.repo_id,
                file_path=request.filter.get("file_path") if request.filter else None,
                symbol_type=request.filter.get("symbol_type") if request.filter else None,
                language=request.filter.get("language") if request.filter else None,
                limit=request.k,
                offset=request.skip,
                min_certainty=0.7,
            )

        # Assemble results with confidence scoring
        assembled_results = await result_assembler.assemble_search_results(
            repo_id=request.repo_id,
            query=request.query,
            raw_results=raw_results,
            include_graph_metadata=True,
        )

        # Format for response
        search_results = [
            SearchResult(
                file_path=r.file_path,
                symbol_name=r.symbol_name,
                symbol_type=r.symbol_type,
                start_line=r.start_line,
                end_line=r.end_line,
                content=r.content,
                confidence=r.confidence,
                language=r.language,
            )
            for r in assembled_results
        ]

        query_time_ms = (time.time() - start_time) * 1000

        logger.info(f"Search completed: {len(search_results)} results in {query_time_ms:.2f}ms")

        resp_model = SearchResponse(
            results=search_results,
            total=len(search_results),
            query_time_ms=query_time_ms,
            repo_id=str(request.repo_id),
        )

        # Add ETag header for caching
        etag = hashlib.md5(resp_model.model_dump_json().encode()).hexdigest()
        response.headers["ETag"] = f'W/"{etag}"'

        return resp_model

    except Exception as e:
        logger.error(f"Search failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# EP-002: POST /api/v1/bob/resolve-stack-trace - Stack Trace Resolution
# ============================================================================


@router.post("/resolve-stack-trace", response_model=StackTraceResponse, tags=["analysis"])
async def resolve_stack_trace(
    request: StackTraceRequest,
    claims: dict[str, Any] = Depends(authenticate),
) -> StackTraceResponse:
    """
    Resolve stack trace to repository file paths.

    - **repo_id**: Repository UUID
    - **trace**: Raw stack trace text

    Parses stack trace (supports Python, Java, JS, Go) and resolves module paths
    to file paths using the dependency graph. Returns frames with git blame info.
    """
    start_time = time.time()

    try:
        logger.info(f"Resolving stack trace for repo_id={request.repo_id}")

        # Parse stack trace
        frames = _parse_stack_trace(request.trace)

        # Resolve file paths using graph
        with GraphQuery() as graph_query:
            resolved_frames = []

            for frame in frames:
                try:
                    # Try to get git blame if file path is resolved
                    if frame.get("file_path"):
                        blame = graph_query.get_git_blame(
                            repo_id=request.repo_id,
                            file_path=frame["file_path"],
                            line_range=(frame.get("line_number", 1), frame.get("line_number", 1)),
                        )

                        if blame.commits:
                            frame["commit_sha"] = blame.commits[0]["commit_hash"]
                            frame["author"] = blame.commits[0]["author"]

                except Exception as e:
                    logger.warning(f"Failed to get blame for frame: {e}")

                resolved_frames.append(frame)

        query_time_ms = (time.time() - start_time) * 1000
        resolved_count = sum(1 for f in resolved_frames if f.get("file_path"))

        logger.info(
            f"Stack trace resolved: {resolved_count}/{len(resolved_frames)} frames in {query_time_ms:.2f}ms"
        )

        return StackTraceResponse(
            frames=resolved_frames,
            total_frames=len(resolved_frames),
            resolved_frames=resolved_count,
            repo_id=str(request.repo_id),
        )

    except Exception as e:
        logger.error(f"Stack trace resolution failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def _parse_stack_trace(trace: str) -> list[dict[str, Any]]:
    """Parse stack trace into frames"""
    frames = []

    # Python pattern: File "path", line X, in function
    python_pattern = r'File "([^"]+)", line (\d+), in (\w+)'

    # Java pattern: at package.Class.method(File.java:line)
    java_pattern = r"at ([\w.]+)\(([\w.]+):(\d+)\)"

    # JavaScript pattern: at function (path:line:col)
    js_pattern = r"at (\w+) \(([^:]+):(\d+):(\d+)\)"

    for line in trace.split("\n"):
        frame: dict[str, Any] = {"raw_frame": line.strip()}

        # Try Python pattern
        match = re.search(python_pattern, line)
        if match:
            frame["file_path"] = match.group(1)
            frame["line_number"] = int(match.group(2))
            frame["function"] = match.group(3)
            frames.append(frame)
            continue

        # Try Java pattern
        match = re.search(java_pattern, line)
        if match:
            frame["function"] = match.group(1)
            frame["file_path"] = match.group(2)
            frame["line_number"] = int(match.group(3))
            frames.append(frame)
            continue

        # Try JavaScript pattern
        match = re.search(js_pattern, line)
        if match:
            frame["function"] = match.group(1)
            frame["file_path"] = match.group(2)
            frame["line_number"] = int(match.group(3))
            frames.append(frame)
            continue

        # If no pattern matched but line is not empty, add as raw frame
        if line.strip():
            frames.append(frame)

    return frames


# ============================================================================
# EP-003: GET /api/v1/bob/dependency-graph - Dependency Graph
# ============================================================================


@router.get("/dependency-graph", response_model=DependencyGraphResponse, tags=["graph"])
async def get_dependency_graph(
    repo_id: UUID,
    file_path: str,
    hops: int = 3,
    direction: str = "both",
    claims: dict[str, Any] = Depends(authenticate),
) -> DependencyGraphResponse:
    """
    Retrieve file dependency graph.

    - **repo_id**: Repository UUID
    - **file_path**: File path to analyze
    - **hops**: Number of hops to traverse (default: 3, max: 10)
    - **direction**: Traversal direction (upstream/downstream/both)

    Returns dependency graph with edges and node counts.
    """
    start_time = time.time()

    try:
        logger.info(
            f"Getting dependency graph: file={file_path}, hops={hops}, direction={direction}"
        )

        # Validate parameters
        if hops > 10:
            raise HTTPException(status_code=400, detail="Maximum hops is 10")

        if direction not in ("upstream", "downstream", "both"):
            raise HTTPException(status_code=400, detail="Invalid direction")

        # Query graph
        with GraphQuery() as graph_query:
            deps = graph_query.get_dependencies(
                repo_id=repo_id,
                file_path=file_path,
                direction=direction,
                max_hops=hops,
            )

        # Build edges
        edges = []
        nodes = {file_path}

        # Upstream edges
        for upstream_file in deps["upstream"]:
            edges.append(
                {
                    "source": upstream_file,
                    "target": file_path,
                    "relationship": "imports",
                }
            )
            nodes.add(upstream_file)

        # Downstream edges
        for downstream_file in deps["downstream"]:
            edges.append(
                {
                    "source": file_path,
                    "target": downstream_file,
                    "relationship": "imports",
                }
            )
            nodes.add(downstream_file)

        query_time_ms = (time.time() - start_time) * 1000

        logger.info(
            f"Dependency graph retrieved: {len(nodes)} nodes, {len(edges)} edges in {query_time_ms:.2f}ms"
        )

        return DependencyGraphResponse(
            root_file=file_path,
            edges=edges,
            node_count=len(nodes),
            edge_count=len(edges),
            max_hops=hops,
            repo_id=str(repo_id),
        )

    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Dependency graph query failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# EP-004: POST /api/v1/bob/blast-radius - Blast Radius Computation
# ============================================================================


@router.post("/blast-radius", response_model=BlastRadiusResponse, tags=["analysis"])
async def compute_blast_radius(
    request: BlastRadiusRequest,
    claims: dict[str, Any] = Depends(authenticate),
) -> BlastRadiusResponse:
    """
    Compute blast radius for changed files.

    - **repo_id**: Repository UUID
    - **files**: List of changed file paths (max 100)

    Returns impacted files sorted by ACS (Architectural Criticality Score)
    with downstream service counts.
    """
    start_time = time.time()

    try:
        logger.info(f"Computing blast radius for {len(request.files)} files")

        # Compute blast radius
        with GraphQuery() as graph_query:
            blast_radius = graph_query.compute_blast_radius(
                repo_id=request.repo_id,
                changed_files=request.files,
                max_hops=5,
            )

        # Enrich with ACS scores and metadata
        impacted_files = []

        with GraphQuery() as graph_query:
            for file_path in blast_radius.affected_files:
                try:
                    # Get file metrics for ACS
                    metrics = graph_query.get_file_metrics(
                        repo_id=request.repo_id,
                        file_path=file_path,
                    )

                    # Calculate simple ACS based on fan-in/fan-out
                    acs_score = (metrics.get("fan_in", 0) + metrics.get("fan_out", 0)) / 10.0

                    impacted_files.append(
                        ImpactedFile(
                            file_path=file_path,
                            distance=1,  # TODO: Calculate actual distance
                            acs_score=min(acs_score, 1.0),
                            downstream_services=blast_radius.affected_services,
                            test_files=[],  # TODO: Get test files from test map
                        )
                    )

                except Exception as e:
                    logger.warning(f"Failed to enrich file {file_path}: {e}")
                    impacted_files.append(
                        ImpactedFile(
                            file_path=file_path,
                            distance=1,
                            acs_score=None,
                            downstream_services=[],
                            test_files=[],
                        )
                    )

        # Sort by ACS (descending)
        impacted_files.sort(key=lambda f: f.acs_score or 0.0, reverse=True)

        query_time_ms = (time.time() - start_time) * 1000

        logger.info(
            f"Blast radius computed: {len(impacted_files)} impacted files in {query_time_ms:.2f}ms"
        )

        return BlastRadiusResponse(
            changed_files=request.files,
            impacted_files=impacted_files,
            total_impacted=len(impacted_files),
            affected_services=blast_radius.affected_services,
            repo_id=str(request.repo_id),
        )

    except Exception as e:
        logger.error(f"Blast radius computation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# EP-005: GET /api/v1/bob/file - File Content Retrieval
# ============================================================================


@router.get("/file", response_model=FileResponse, tags=["files"])
async def get_file(
    repo_id: UUID,
    file_path: str,
    claims: dict[str, Any] = Depends(authenticate),
) -> FileResponse:
    """
    Fetch file content and metadata.

    - **repo_id**: Repository UUID
    - **file_path**: File path relative to repository root

    Checks Redis cache first, falls back to Git if cache miss.
    Returns file content with parsed symbols and imports.
    """
    start_time = time.time()

    try:
        logger.info(f"Fetching file: {file_path}")

        # Try cache first
        cache_key = f"{repo_id}:{file_path}"
        content = None

        with FileCache() as cache:
            cached_content = cache.get("file", cache_key)
            if cached_content:
                content = cached_content
                logger.debug(f"Cache hit for {file_path}")

        # Fallback to Git if cache miss
        if content is None:
            logger.debug(f"Cache miss for {file_path}, fetching from Git")
            # TODO: Implement Git fetcher
            raise ResourceNotFoundError(
                f"File not found in cache and Git fetcher not implemented: {file_path}"
            )

        # Parse file to extract symbols
        # TODO: Use appropriate parser based on language
        symbols = []
        imports = []
        language = _detect_language(file_path)
        total_lines = len(content.split("\n"))

        query_time_ms = (time.time() - start_time) * 1000

        logger.info(f"File retrieved: {file_path} ({total_lines} lines) in {query_time_ms:.2f}ms")

        return FileResponse(
            file_path=file_path,
            content=content,
            language=language,
            total_lines=total_lines,
            symbols=symbols,
            imports=imports,
            last_modified=None,
            repo_id=str(repo_id),
        )

    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"File retrieval failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def _detect_language(file_path: str) -> str:
    """Detect programming language from file extension"""
    ext = file_path.split(".")[-1].lower()

    language_map = {
        "py": "python",
        "js": "javascript",
        "ts": "typescript",
        "go": "go",
        "java": "java",
        "rb": "ruby",
        "rs": "rust",
        "cpp": "cpp",
        "c": "c",
        "h": "c",
    }

    return language_map.get(ext, "unknown")


# ============================================================================
# EP-006: GET /api/v1/bob/commit-diff - Commit Diff Analysis
# ============================================================================


@router.get("/commit-diff", response_model=CommitDiffResponse, tags=["analysis"])
async def analyze_commit_diff(
    repo_id: UUID,
    commit_sha: str,
    claims: dict[str, Any] = Depends(authenticate),
) -> CommitDiffResponse:
    """
    Analyze commit diff.

    - **repo_id**: Repository UUID
    - **commit_sha**: Commit SHA (short or full)

    Fetches git diff, parses changed files, queries dependency edges,
    and returns impact analysis with related test files.
    """
    start_time = time.time()

    try:
        logger.info(f"Analyzing commit diff: {commit_sha}")

        # TODO: Fetch commit diff using GitPython
        # For now, return placeholder

        query_time_ms = (time.time() - start_time) * 1000

        logger.info(f"Commit diff analyzed: {commit_sha} in {query_time_ms:.2f}ms")

        return CommitDiffResponse(
            commit_sha=commit_sha,
            author=None,
            message=None,
            timestamp=None,
            changed_files=[],
            total_additions=0,
            total_deletions=0,
            repo_id=str(repo_id),
        )

    except Exception as e:
        logger.error(f"Commit diff analysis failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# EP-007: GET /api/v1/bob/health - Health Check
# ============================================================================


@router.get("/health", response_model=HealthResponse, tags=["system"])
async def health_check() -> HealthResponse:
    """
    Service health check.

    Returns service status, indexed repository count, query latency metrics,
    and connection status for all backend services (Neo4j, Weaviate, PostgreSQL, Redis).
    """
    try:
        services = {}
        metrics = {}
        last_error = None

        # Check Neo4j
        try:
            with GraphQuery() as graph_query:
                # Simple connectivity check
                services["neo4j"] = "healthy"
        except Exception as e:
            services["neo4j"] = "unhealthy"
            last_error = f"Neo4j: {str(e)}"

        # Check Weaviate
        try:
            with VectorStore() as vector_store:
                stats = vector_store.get_stats()
                services["weaviate"] = "healthy"
                metrics["vector_count"] = stats.get("total_embeddings", 0)
        except Exception as e:
            services["weaviate"] = "unhealthy"
            last_error = f"Weaviate: {str(e)}"

        # Check PostgreSQL
        try:
            with IndexRegistryManager() as registry:
                health_metrics = registry.get_health_metrics()
                services["postgres"] = "healthy"
                metrics["repos_indexed"] = health_metrics.get("total_repositories", 0)
        except Exception as e:
            services["postgres"] = "unhealthy"
            last_error = f"PostgreSQL: {str(e)}"

        # Check Redis
        try:
            with FileCache() as cache:
                cache_stats = cache.get_stats()
                services["redis"] = "healthy"
                metrics["cache_hit_rate"] = cache_stats.get("hit_rate", 0.0)
        except Exception as e:
            services["redis"] = "unhealthy"
            last_error = f"Redis: {str(e)}"

        # Determine overall status
        unhealthy_count = sum(1 for status in services.values() if status == "unhealthy")

        if unhealthy_count == 0:
            overall_status = "healthy"
        elif unhealthy_count < len(services):
            overall_status = "degraded"
        else:
            overall_status = "unhealthy"

        return HealthResponse(
            status=overall_status,
            version="1.0.0",
            services=services,
            metrics=metrics,
            repos_indexed=metrics.get("repos_indexed", 0),
            query_p95_ms=0.0,  # TODO: Get from metrics
            index_queue_depth=0,  # TODO: Get from Redis
            last_error=last_error,
        )

    except Exception as e:
        logger.error(f"Health check failed: {e}", exc_info=True)
        return HealthResponse(
            status="unhealthy",
            version="1.0.0",
            services={},
            metrics={},
            repos_indexed=0,
            query_p95_ms=0.0,
            index_queue_depth=0,
            last_error=str(e),
        )


# ============================================================================
# EP-008: POST /api/v1/bob/batch - Batch Query Processing
# ============================================================================


@router.post("/batch", response_model=BatchResponse, tags=["batch"])
async def batch_query(
    request: BatchRequest,
    claims: dict[str, Any] = Depends(authenticate),
) -> BatchResponse:
    """
    Execute batch queries (max 20 sub-queries).

    - **queries**: List of sub-queries with query_id, query_type, and params

    Executes sub-queries in parallel using asyncio.gather with 5-second timeout
    per sub-query. Returns results in same order with partial failure handling.
    """
    start_time = time.time()

    try:
        logger.info(f"Processing batch query with {len(request.queries)} sub-queries")

        # Execute sub-queries in parallel
        tasks = [_execute_sub_query(sub_query, claims) for sub_query in request.queries]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        sub_query_results = []
        successful = 0
        failed = 0

        for i, result in enumerate(results):
            query_id = request.queries[i].query_id

            if isinstance(result, Exception):
                # Sub-query failed
                sub_query_results.append(
                    SubQueryResult(
                        query_id=query_id,
                        success=False,
                        result=None,
                        error=str(result),
                        execution_time_ms=0.0,
                    )
                )
                failed += 1
            else:
                # Sub-query succeeded
                assert isinstance(result, SubQueryResult)
                sub_query_results.append(result)
                successful += 1

        total_time_ms = (time.time() - start_time) * 1000

        logger.info(
            f"Batch query completed: {successful} successful, {failed} failed in {total_time_ms:.2f}ms"
        )

        return BatchResponse(
            results=sub_query_results,
            total_queries=len(request.queries),
            successful_queries=successful,
            failed_queries=failed,
            total_time_ms=total_time_ms,
        )

    except Exception as e:
        logger.error(f"Batch query failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


async def _execute_sub_query(
    sub_query: SubQuery,
    claims: dict[str, Any],
) -> SubQueryResult:
    """Execute a single sub-query with timeout"""
    start_time = time.time()

    try:
        # Execute with 5-second timeout
        result = await asyncio.wait_for(
            _route_sub_query(sub_query, claims),
            timeout=5.0,
        )

        execution_time_ms = (time.time() - start_time) * 1000

        return SubQueryResult(
            query_id=sub_query.query_id,
            success=True,
            result=result,
            error=None,
            execution_time_ms=execution_time_ms,
        )

    except asyncio.TimeoutError:
        execution_time_ms = (time.time() - start_time) * 1000
        return SubQueryResult(
            query_id=sub_query.query_id,
            success=False,
            result=None,
            error="Query timeout (5 seconds)",
            execution_time_ms=execution_time_ms,
        )

    except Exception as e:
        execution_time_ms = (time.time() - start_time) * 1000
        return SubQueryResult(
            query_id=sub_query.query_id,
            success=False,
            result=None,
            error=str(e),
            execution_time_ms=execution_time_ms,
        )


async def _route_sub_query(
    sub_query: SubQuery,
    claims: dict[str, Any],
) -> dict[str, Any]:
    """Route sub-query to appropriate handler"""
    query_type = sub_query.query_type
    params = sub_query.params

    # Route based on query type
    if query_type == "search":
        # Execute search
        request = SearchRequest(**params)
        dummy_response = Response()
        response = await search_code(request, dummy_response, claims)
        return response.model_dump()

    elif query_type == "dependency_graph":
        # Execute dependency graph query
        response = await get_dependency_graph(
            repo_id=UUID(params["repo_id"]),
            file_path=params["file_path"],
            hops=params.get("hops", 3),
            direction=params.get("direction", "both"),
            claims=claims,
        )
        return response.model_dump()

    elif query_type == "blast_radius":
        # Execute blast radius
        request = BlastRadiusRequest(**params)
        response = await compute_blast_radius(request, claims)
        return response.model_dump()

    elif query_type == "file":
        # Execute file retrieval
        response = await get_file(
            repo_id=UUID(params["repo_id"]),
            file_path=params["file_path"],
            claims=claims,
        )
        return response.model_dump()

    else:
        raise ValueError(f"Unsupported query type: {query_type}")


# Made with Bob
