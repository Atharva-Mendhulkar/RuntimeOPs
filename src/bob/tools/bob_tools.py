"""
IBM Bob - Agent Tool Suite
10 tools for RuntimeOps agents to interact with Bob's knowledge graph
"""

import logging
import time
from typing import Any
from uuid import UUID

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from bob.config import get_settings
from bob.exceptions import (
    QueryError,
    QueryTimeoutError,
    ResourceNotFoundError,
)
from bob.graph.query import GraphQuery
from bob.storage.cache import FileCache
from bob.tools.models import (
    BlastRadiusResult,
    CodeSearchResult,
    CommitDiff,
    DependencyGraph,
    FileContent,
    RiskContext,
    StackFrame,
)

logger = logging.getLogger(__name__)
settings = get_settings()


# ============================================================================
# Tool 1: Semantic Search
# ============================================================================


@retry(
    retry=retry_if_exception_type((httpx.HTTPError, QueryError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=4),
)
def semantic_search(
    query: str,
    repo_id: str,
    k: int = 10,
) -> list[CodeSearchResult]:
    """
    Search code semantically across repository.

    Uses vector embeddings to find code units matching the natural language query.
    Returns top-K results with confidence scores.

    Args:
        query: Natural language search query (e.g., "authentication middleware")
        repo_id: Repository UUID to search within
        k: Number of results to return (default: 10, max: 50)

    Returns:
        List of CodeSearchResult objects with file paths, symbols, and confidence scores

    Raises:
        QueryError: If search fails
        QueryTimeoutError: If search times out

    Example:
        >>> results = semantic_search(
        ...     query="database connection pool",
        ...     repo_id="550e8400-e29b-41d4-a716-446655440000",
        ...     k=5
        ... )
        >>> for result in results:
        ...     print(f"{result.file_path}:{result.symbol_name} (confidence: {result.confidence})")
    """
    start_time = time.time()

    try:
        logger.info(f"Semantic search: query='{query[:50]}...', repo_id={repo_id}, k={k}")

        # Call REST endpoint EP-001
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{settings.bob_api_url}/api/v1/bob/search",
                json={
                    "repo_id": repo_id,
                    "query": query,
                    "k": min(k, 50),
                },
                headers={"Authorization": f"Bearer {settings.bob_api_key}"},
            )
            response.raise_for_status()
            data = response.json()

        # Convert to CodeSearchResult models
        results = [
            CodeSearchResult(
                file_path=r["file_path"],
                symbol_name=r["symbol_name"],
                symbol_type=r["symbol_type"],
                start_line=r["start_line"],
                end_line=r["end_line"],
                content=r["content"],
                confidence=r["confidence"],
                language=r["language"],
                metadata={},
            )
            for r in data["results"]
        ]

        elapsed_ms = (time.time() - start_time) * 1000
        logger.info(f"Semantic search completed: {len(results)} results in {elapsed_ms:.2f}ms")

        return results

    except httpx.TimeoutException as e:
        raise QueryTimeoutError(f"Semantic search timed out: {e}")
    except httpx.HTTPError as e:
        raise QueryError(f"Semantic search failed: {e}")
    except Exception as e:
        logger.error(f"Semantic search error: {e}", exc_info=True)
        raise QueryError(f"Semantic search failed: {e}")


# ============================================================================
# Tool 2: Resolve Stack Trace
# ============================================================================


@retry(
    retry=retry_if_exception_type((httpx.HTTPError, QueryError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=4),
)
def resolve_stack_trace(
    trace_text: str,
    repo_id: str,
) -> list[StackFrame]:
    """
    Resolve stack trace to repository file paths.

    Parses stack trace (supports Python, Java, JS, Go) and resolves module paths
    to file paths using the dependency graph. Returns frames with git blame info.

    Args:
        trace_text: Raw stack trace text
        repo_id: Repository UUID

    Returns:
        List of StackFrame objects with resolved file paths and git blame

    Raises:
        QueryError: If resolution fails

    Example:
        >>> trace = '''
        ... Traceback (most recent call last):
        ...   File "app.py", line 42, in handler
        ...     process_request()
        ... '''
        >>> frames = resolve_stack_trace(trace, repo_id="550e8400-...")
        >>> for frame in frames:
        ...     if frame.file_path:
        ...         print(f"{frame.file_path}:{frame.line_number} in {frame.function}")
    """
    start_time = time.time()

    try:
        logger.info(f"Resolving stack trace for repo_id={repo_id}")

        # Call REST endpoint EP-002
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{settings.bob_api_url}/api/v1/bob/resolve-stack-trace",
                json={
                    "repo_id": repo_id,
                    "trace": trace_text,
                },
                headers={"Authorization": f"Bearer {settings.bob_api_key}"},
            )
            response.raise_for_status()
            data = response.json()

        # Convert to StackFrame models
        frames = [
            StackFrame(
                file_path=f.get("file_path"),
                line_number=f.get("line_number"),
                function=f.get("function"),
                commit_sha=f.get("commit_sha"),
                author=f.get("author"),
                raw_frame=f["raw_frame"],
            )
            for f in data["frames"]
        ]

        elapsed_ms = (time.time() - start_time) * 1000
        resolved_count = sum(1 for f in frames if f.file_path)
        logger.info(
            f"Stack trace resolved: {resolved_count}/{len(frames)} frames in {elapsed_ms:.2f}ms"
        )

        return frames

    except httpx.HTTPError as e:
        raise QueryError(f"Stack trace resolution failed: {e}")
    except Exception as e:
        logger.error(f"Stack trace resolution error: {e}", exc_info=True)
        raise QueryError(f"Stack trace resolution failed: {e}")


# ============================================================================
# Tool 3: Get Dependency Graph
# ============================================================================


@retry(
    retry=retry_if_exception_type((httpx.HTTPError, QueryError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=4),
)
def get_dependency_graph(
    file_path: str,
    repo_id: str,
    hops: int = 3,
    direction: str = "both",
) -> DependencyGraph:
    """
    Retrieve file dependency graph.

    Traverses Neo4j graph to find dependencies within N hops.
    Returns adjacency list of dependency edges.

    Args:
        file_path: File path to analyze
        repo_id: Repository UUID
        hops: Number of hops to traverse (default: 3, max: 10)
        direction: Traversal direction ('upstream', 'downstream', or 'both')

    Returns:
        DependencyGraph with edges and node counts

    Raises:
        QueryError: If graph query fails

    Example:
        >>> graph = get_dependency_graph(
        ...     file_path="src/auth/middleware.py",
        ...     repo_id="550e8400-...",
        ...     hops=3,
        ...     direction="both"
        ... )
        >>> print(f"Found {graph.node_count} nodes and {graph.edge_count} edges")
    """
    start_time = time.time()

    try:
        logger.info(
            f"Getting dependency graph: file={file_path}, hops={hops}, direction={direction}"
        )

        # Call REST endpoint EP-003
        with httpx.Client(timeout=30.0) as client:
            response = client.get(
                f"{settings.bob_api_url}/api/v1/bob/dependency-graph",
                params={
                    "repo_id": repo_id,
                    "file_path": file_path,
                    "hops": min(hops, 10),
                    "direction": direction,
                },
                headers={"Authorization": f"Bearer {settings.bob_api_key}"},
            )
            response.raise_for_status()
            data = response.json()

        # Convert to DependencyGraph model
        from bob.tools.models import DependencyEdge

        edges = [
            DependencyEdge(
                source=e["source"],
                target=e["target"],
                relationship=e["relationship"],
                metadata={},
            )
            for e in data["edges"]
        ]

        # Extract unique nodes from edges
        nodes = {file_path}
        for edge in edges:
            nodes.add(edge.source)
            nodes.add(edge.target)

        graph = DependencyGraph(
            root_file=file_path,
            edges=edges,
            nodes=list(nodes),
            node_count=len(nodes),
            edge_count=len(edges),
            max_hops=hops,
        )

        elapsed_ms = (time.time() - start_time) * 1000
        logger.info(
            f"Dependency graph retrieved: {graph.node_count} nodes, "
            f"{graph.edge_count} edges in {elapsed_ms:.2f}ms"
        )

        return graph

    except httpx.HTTPError as e:
        raise QueryError(f"Dependency graph query failed: {e}")
    except Exception as e:
        logger.error(f"Dependency graph error: {e}", exc_info=True)
        raise QueryError(f"Dependency graph query failed: {e}")


# ============================================================================
# Tool 4: Get Blast Radius
# ============================================================================


@retry(
    retry=retry_if_exception_type((httpx.HTTPError, QueryError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=4),
)
def get_blast_radius(
    files: list[str],
    repo_id: str,
) -> BlastRadiusResult:
    """
    Compute blast radius for changed files.

    Computes union of downstream dependency subgraphs for a list of files.
    Returns sorted list with ACS (Architectural Criticality Score) weights.

    Args:
        files: List of changed file paths (max 100)
        repo_id: Repository UUID

    Returns:
        BlastRadiusResult with impacted files sorted by ACS

    Raises:
        QueryError: If blast radius computation fails

    Example:
        >>> result = get_blast_radius(
        ...     files=["src/db/models/user.py"],
        ...     repo_id="550e8400-..."
        ... )
        >>> print(f"Total impacted: {result.total_impacted} files")
        >>> for file in result.impacted_files[:5]:
        ...     print(f"{file.file_path} (ACS: {file.acs_score})")
    """
    start_time = time.time()

    try:
        logger.info(f"Computing blast radius for {len(files)} files")

        # Call REST endpoint EP-004
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{settings.bob_api_url}/api/v1/bob/blast-radius",
                json={
                    "repo_id": repo_id,
                    "files": files[:100],  # Limit to 100 files
                },
                headers={"Authorization": f"Bearer {settings.bob_api_key}"},
            )
            response.raise_for_status()
            data = response.json()

        # Convert to BlastRadiusResult model
        from bob.tools.models import ImpactedFile

        impacted_files = [
            ImpactedFile(
                file_path=f["file_path"],
                distance=f["distance"],
                acs_score=f.get("acs_score"),
                downstream_services=f.get("downstream_services", []),
                test_files=f.get("test_files", []),
            )
            for f in data["impacted_files"]
        ]

        result = BlastRadiusResult(
            changed_files=data["changed_files"],
            impacted_files=impacted_files,
            total_impacted=data["total_impacted"],
            affected_services=data["affected_services"],
        )

        elapsed_ms = (time.time() - start_time) * 1000
        logger.info(
            f"Blast radius computed: {result.total_impacted} impacted files in {elapsed_ms:.2f}ms"
        )

        return result

    except httpx.HTTPError as e:
        raise QueryError(f"Blast radius computation failed: {e}")
    except Exception as e:
        logger.error(f"Blast radius error: {e}", exc_info=True)
        raise QueryError(f"Blast radius computation failed: {e}")


# ============================================================================
# Tool 5: Get File Content
# ============================================================================


@retry(
    retry=retry_if_exception_type((httpx.HTTPError, QueryError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=4),
)
def get_file_content(
    file_path: str,
    repo_id: str,
) -> FileContent:
    """
    Fetch file content and metadata.

    Checks Redis cache first, falls back to Git if cache miss.
    Returns file content with parsed symbols (functions, classes, imports).

    Args:
        file_path: File path relative to repository root
        repo_id: Repository UUID

    Returns:
        FileContent with content and parsed metadata

    Raises:
        ResourceNotFoundError: If file not found
        QueryError: If retrieval fails

    Example:
        >>> content = get_file_content(
        ...     file_path="src/auth/middleware.py",
        ...     repo_id="550e8400-..."
        ... )
        >>> print(f"File has {len(content.symbols)} symbols")
        >>> print(f"Imports: {', '.join(content.imports)}")
    """
    start_time = time.time()

    try:
        logger.info(f"Fetching file content: {file_path}")

        # Call REST endpoint EP-005
        with httpx.Client(timeout=30.0) as client:
            response = client.get(
                f"{settings.bob_api_url}/api/v1/bob/file",
                params={
                    "repo_id": repo_id,
                    "file_path": file_path,
                },
                headers={"Authorization": f"Bearer {settings.bob_api_key}"},
            )

            if response.status_code == 404:
                raise ResourceNotFoundError(f"File not found: {file_path}")

            response.raise_for_status()
            data = response.json()

        # Convert to FileContent model
        from bob.tools.models import FileSymbol

        symbols = [
            FileSymbol(
                name=s["name"],
                type=s["type"],
                start_line=s["start_line"],
                end_line=s["end_line"],
                docstring=None,
            )
            for s in data.get("symbols", [])
        ]

        content = FileContent(
            file_path=data["file_path"],
            content=data["content"],
            language=data["language"],
            total_lines=data["total_lines"],
            symbols=symbols,
            imports=data.get("imports", []),
            last_modified=None,
        )

        elapsed_ms = (time.time() - start_time) * 1000
        logger.info(f"File content retrieved: {file_path} in {elapsed_ms:.2f}ms")

        return content

    except httpx.HTTPError as e:
        if e.response and e.response.status_code == 404:
            raise ResourceNotFoundError(f"File not found: {file_path}")
        raise QueryError(f"File retrieval failed: {e}")
    except Exception as e:
        logger.error(f"File retrieval error: {e}", exc_info=True)
        raise QueryError(f"File retrieval failed: {e}")


# ============================================================================
# Tool 6: Get Commit Diff
# ============================================================================


@retry(
    retry=retry_if_exception_type((httpx.HTTPError, QueryError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=4),
)
def get_commit_diff(
    commit_sha: str,
    repo_id: str,
) -> CommitDiff:
    """
    Fetch git diff for commit with impact analysis.

    Fetches git diff, parses changed files, queries dependency edges,
    and returns impact analysis with related test files.

    Args:
        commit_sha: Commit SHA (short or full)
        repo_id: Repository UUID

    Returns:
        CommitDiff with changed files and impact analysis

    Raises:
        QueryError: If commit diff retrieval fails

    Example:
        >>> diff = get_commit_diff(
        ...     commit_sha="abc123",
        ...     repo_id="550e8400-..."
        ... )
        >>> print(f"Commit by {diff.author}: {diff.message}")
        >>> print(f"Changed {len(diff.changed_files)} files")
    """
    start_time = time.time()

    try:
        logger.info(f"Fetching commit diff: {commit_sha}")

        # Call REST endpoint EP-006
        with httpx.Client(timeout=30.0) as client:
            response = client.get(
                f"{settings.bob_api_url}/api/v1/bob/commit-diff",
                params={
                    "repo_id": repo_id,
                    "commit_sha": commit_sha,
                },
                headers={"Authorization": f"Bearer {settings.bob_api_key}"},
            )
            response.raise_for_status()
            data = response.json()

        # Convert to CommitDiff model
        from bob.tools.models import ChangedFile

        changed_files = [
            ChangedFile(
                file_path=f["file_path"],
                change_type=f["change_type"],
                additions=f["additions"],
                deletions=f["deletions"],
                impacted_files=f.get("impacted_files", []),
                test_files=f.get("test_files", []),
            )
            for f in data.get("changed_files", [])
        ]

        diff = CommitDiff(
            commit_sha=data["commit_sha"],
            author=data.get("author"),
            message=data.get("message"),
            timestamp=None,
            changed_files=changed_files,
            total_additions=data.get("total_additions", 0),
            total_deletions=data.get("total_deletions", 0),
        )

        elapsed_ms = (time.time() - start_time) * 1000
        logger.info(f"Commit diff retrieved: {commit_sha} in {elapsed_ms:.2f}ms")

        return diff

    except httpx.HTTPError as e:
        raise QueryError(f"Commit diff retrieval failed: {e}")
    except Exception as e:
        logger.error(f"Commit diff error: {e}", exc_info=True)
        raise QueryError(f"Commit diff retrieval failed: {e}")


# ============================================================================
# Tool 7: Get Test Map
# ============================================================================


@retry(
    retry=retry_if_exception_type(QueryError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=4),
)
def get_test_map(
    source_files: list[str],
    repo_id: str,
) -> list[str]:
    """
    Get test files that import or reference source files.

    Queries Neo4j for test files using naming conventions (test_*.py, *.test.ts)
    and import relationships.

    Args:
        source_files: List of source file paths
        repo_id: Repository UUID

    Returns:
        List of test file paths

    Raises:
        QueryError: If test map query fails

    Example:
        >>> tests = get_test_map(
        ...     source_files=["src/auth/middleware.py"],
        ...     repo_id="550e8400-..."
        ... )
        >>> print(f"Found {len(tests)} test files")
    """
    start_time = time.time()

    try:
        logger.info(f"Getting test map for {len(source_files)} source files")

        # Query Neo4j for test files
        with GraphQuery() as graph_query:
            test_files = set()

            for source_file in source_files:
                # Get files that import this source file
                deps = graph_query.get_dependencies(
                    repo_id=UUID(repo_id),
                    file_path=source_file,
                    direction="downstream",
                    max_hops=2,
                )

                # Filter for test files using naming conventions
                for downstream_file in deps.get("downstream", []):
                    if _is_test_file(downstream_file):
                        test_files.add(downstream_file)

        result = sorted(list(test_files))

        elapsed_ms = (time.time() - start_time) * 1000
        logger.info(f"Test map retrieved: {len(result)} test files in {elapsed_ms:.2f}ms")

        return result

    except Exception as e:
        logger.error(f"Test map error: {e}", exc_info=True)
        raise QueryError(f"Test map query failed: {e}")


def _is_test_file(file_path: str) -> bool:
    """Check if file is a test file based on naming conventions"""
    file_name = file_path.split("/")[-1].lower()

    # Python: test_*.py, *_test.py
    if file_name.startswith("test_") and file_name.endswith(".py"):
        return True
    if file_name.endswith("_test.py"):
        return True

    # JavaScript/TypeScript: *.test.js, *.test.ts, *.spec.js, *.spec.ts
    if file_name.endswith((".test.js", ".test.ts", ".spec.js", ".spec.ts")):
        return True

    # Java: *Test.java
    if file_name.endswith("test.java"):
        return True

    # Go: *_test.go
    if file_name.endswith("_test.go"):
        return True

    # Check if in test directory
    if "/test/" in file_path or "/tests/" in file_path:
        return True

    return False


# ============================================================================
# Tool 8: Get Conventions
# ============================================================================


@retry(
    retry=retry_if_exception_type(QueryError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=4),
)
def get_conventions(
    service_path: str,
    repo_id: str,
) -> dict[str, Any]:
    """
    Get coding conventions for a service.

    Fetches from Redis cache (24-hour TTL). Returns naming conventions,
    error handling patterns, and import order conventions.

    Args:
        service_path: Service path (e.g., "services/auth")
        repo_id: Repository UUID

    Returns:
        Dictionary with naming, error handling, and import conventions

    Raises:
        QueryError: If conventions retrieval fails

    Example:
        >>> conventions = get_conventions(
        ...     service_path="services/auth",
        ...     repo_id="550e8400-..."
        ... )
        >>> print(f"Naming: {conventions['naming']}")
        >>> print(f"Error handling: {conventions['error_handling']}")
    """
    start_time = time.time()

    try:
        logger.info(f"Getting conventions for service: {service_path}")

        # Try cache first
        cache_key = f"conventions:{repo_id}:{service_path}"

        with FileCache() as cache:
            cached_conventions = cache.get("conventions", cache_key)

            if cached_conventions:
                logger.debug(f"Cache hit for conventions: {service_path}")
                return cached_conventions

        # Cache miss - query from ingestion layer
        # TODO: Implement convention extraction from ingestion layer
        # For now, return default conventions
        conventions = {
            "naming": {
                "functions": "snake_case",
                "classes": "PascalCase",
                "constants": "UPPER_SNAKE_CASE",
            },
            "error_handling": {
                "pattern": "try-except with logging",
                "custom_exceptions": True,
            },
            "import_order": {
                "order": ["stdlib", "third_party", "local"],
                "style": "absolute",
            },
        }

        # Cache for 24 hours
        with FileCache() as cache:
            cache.set("conventions", cache_key, conventions, ttl=86400)

        elapsed_ms = (time.time() - start_time) * 1000
        logger.info(f"Conventions retrieved for {service_path} in {elapsed_ms:.2f}ms")

        return conventions

    except Exception as e:
        logger.error(f"Conventions retrieval error: {e}", exc_info=True)
        raise QueryError(f"Conventions retrieval failed: {e}")


# ============================================================================
# Tool 9: Get Risk Context
# ============================================================================


@retry(
    retry=retry_if_exception_type(QueryError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=4),
)
def get_risk_context(
    files: list[str],
    repo_id: str,
) -> list[RiskContext]:
    """
    Get risk context for files.

    Queries Neo4j for ACS scores and downstream service counts.
    Queries PostgreSQL for last-incident association.
    Returns risk metadata per file.

    Args:
        files: List of file paths
        repo_id: Repository UUID

    Returns:
        List of RiskContext objects with risk metadata

    Raises:
        QueryError: If risk context query fails

    Example:
        >>> contexts = get_risk_context(
        ...     files=["src/db/models/user.py"],
        ...     repo_id="550e8400-..."
        ... )
        >>> for ctx in contexts:
        ...     print(f"{ctx.file_path}: {ctx.risk_level} (ACS: {ctx.acs_score})")
    """
    start_time = time.time()

    try:
        logger.info(f"Getting risk context for {len(files)} files")

        risk_contexts = []

        with GraphQuery() as graph_query:
            for file_path in files:
                try:
                    # Get file metrics for ACS
                    metrics = graph_query.get_file_metrics(
                        repo_id=UUID(repo_id),
                        file_path=file_path,
                    )

                    # Calculate ACS based on fan-in/fan-out
                    fan_in = metrics.get("fan_in", 0)
                    fan_out = metrics.get("fan_out", 0)
                    acs_score = min((fan_in + fan_out) / 10.0, 1.0)

                    # Get downstream service count
                    deps = graph_query.get_dependencies(
                        repo_id=UUID(repo_id),
                        file_path=file_path,
                        direction="downstream",
                        max_hops=5,
                    )
                    downstream_count = len(deps.get("downstream", []))

                    # Determine risk level
                    if acs_score >= 0.8 or downstream_count >= 10:
                        risk_level = "CRITICAL"
                    elif acs_score >= 0.6 or downstream_count >= 5:
                        risk_level = "HIGH"
                    elif acs_score >= 0.4 or downstream_count >= 2:
                        risk_level = "MEDIUM"
                    else:
                        risk_level = "LOW"

                    risk_contexts.append(
                        RiskContext(
                            file_path=file_path,
                            acs_score=acs_score,
                            downstream_service_count=downstream_count,
                            last_incident_date=None,  # TODO: Query from PostgreSQL
                            incident_count=0,
                            change_frequency=None,
                            risk_level=risk_level,
                        )
                    )

                except Exception as e:
                    logger.warning(f"Failed to get risk context for {file_path}: {e}")
                    # Add default risk context
                    risk_contexts.append(
                        RiskContext(
                            file_path=file_path,
                            acs_score=None,
                            downstream_service_count=0,
                            last_incident_date=None,
                            incident_count=0,
                            change_frequency=None,
                            risk_level="MEDIUM",
                        )
                    )

        elapsed_ms = (time.time() - start_time) * 1000
        logger.info(f"Risk context retrieved for {len(files)} files in {elapsed_ms:.2f}ms")

        return risk_contexts

    except Exception as e:
        logger.error(f"Risk context error: {e}", exc_info=True)
        raise QueryError(f"Risk context query failed: {e}")


# ============================================================================
# Tool 10: Trigger Reindex
# ============================================================================


@retry(
    retry=retry_if_exception_type(QueryError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=4),
)
def trigger_reindex(
    repo_id: str,
    scope: str = "incremental",
) -> str:
    """
    Trigger repository reindexing.

    Enqueues an ingest job in Redis queue. Returns job_id for status polling.

    Args:
        repo_id: Repository UUID
        scope: Reindex scope ('incremental' or 'full')

    Returns:
        Job ID for status polling

    Raises:
        QueryError: If reindex trigger fails

    Example:
        >>> job_id = trigger_reindex(
        ...     repo_id="550e8400-...",
        ...     scope="incremental"
        ... )
        >>> print(f"Reindex job started: {job_id}")
    """
    start_time = time.time()

    try:
        logger.info(f"Triggering reindex: repo_id={repo_id}, scope={scope}")

        if scope not in ("incremental", "full"):
            raise QueryError(f"Invalid scope: {scope}. Must be 'incremental' or 'full'")

        # Enqueue job in Redis
        import uuid

        job_id = str(uuid.uuid4())

        with FileCache() as cache:
            # Store job in queue
            job_data = {
                "job_id": job_id,
                "repo_id": repo_id,
                "scope": scope,
                "status": "queued",
                "created_at": time.time(),
            }

            # Add to queue (using Redis list as queue)
            cache.redis_client.lpush("ingest_queue", str(job_data))

            # Store job status
            cache.set("job_status", job_id, job_data, ttl=86400)

        elapsed_ms = (time.time() - start_time) * 1000
        logger.info(f"Reindex triggered: job_id={job_id} in {elapsed_ms:.2f}ms")

        return job_id

    except Exception as e:
        logger.error(f"Reindex trigger error: {e}", exc_info=True)
        raise QueryError(f"Reindex trigger failed: {e}")


# Made with Bob
