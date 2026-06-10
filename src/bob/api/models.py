"""
IBM Bob - API Request/Response Models
Pydantic models for all REST endpoints with validation and examples
"""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


# ============================================================================
# Search Models (EP-001)
# ============================================================================


class SearchRequest(BaseModel):
    """Request model for semantic code search"""

    repo_id: UUID = Field(
        ...,
        description="Repository UUID to search within",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )
    query: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="Natural language search query",
        examples=["authentication middleware", "database connection pool"],
    )
    k: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Number of results to return",
    )
    skip: int = Field(
        default=0,
        ge=0,
        description="Number of results to skip for pagination",
    )
    filter: dict[str, Any] | None = Field(
        default=None,
        description="Optional filters (file_path, language, symbol_type)",
        examples=[{"language": "python", "symbol_type": "function"}],
    )


class SearchResult(BaseModel):
    """Individual search result"""

    file_path: str = Field(..., description="File path relative to repository root")
    symbol_name: str = Field(..., description="Symbol name (function, class, etc.)")
    symbol_type: str = Field(..., description="Symbol type (function, class, method)")
    start_line: int = Field(..., description="Start line number")
    end_line: int = Field(..., description="End line number")
    content: str = Field(..., description="Code snippet")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")
    language: str = Field(..., description="Programming language")


class SearchResponse(BaseModel):
    """Response model for semantic code search"""

    results: list[SearchResult] = Field(..., description="Search results")
    total: int = Field(..., description="Total number of results")
    query_time_ms: float = Field(..., description="Query execution time in milliseconds")
    repo_id: str = Field(..., description="Repository UUID")


# ============================================================================
# Stack Trace Models (EP-002)
# ============================================================================


class StackTraceRequest(BaseModel):
    """Request model for stack trace resolution"""

    repo_id: UUID = Field(
        ...,
        description="Repository UUID",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )
    trace: str = Field(
        ...,
        min_length=10,
        description="Raw stack trace text",
        examples=[
            "Traceback (most recent call last):\n  File 'app.py', line 42, in handler\n    process_request()"
        ],
    )


class StackFrame(BaseModel):
    """Individual stack frame"""

    file_path: str | None = Field(None, description="Resolved file path")
    line_number: int | None = Field(None, description="Line number")
    function: str | None = Field(None, description="Function name")
    commit_sha: str | None = Field(None, description="Last commit SHA for this line")
    author: str | None = Field(None, description="Author of last change")
    raw_frame: str = Field(..., description="Original raw frame text")


class StackTraceResponse(BaseModel):
    """Response model for stack trace resolution"""

    frames: list[StackFrame] = Field(..., description="Resolved stack frames")
    total_frames: int = Field(..., description="Total number of frames")
    resolved_frames: int = Field(..., description="Number of successfully resolved frames")
    repo_id: str = Field(..., description="Repository UUID")


# ============================================================================
# Dependency Graph Models (EP-003)
# ============================================================================


class DependencyGraphRequest(BaseModel):
    """Request model for dependency graph retrieval"""

    repo_id: UUID = Field(..., description="Repository UUID")
    file_path: str = Field(..., description="File path to analyze")
    hops: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Number of hops to traverse",
    )
    direction: Literal["upstream", "downstream", "both"] = Field(
        default="both",
        description="Traversal direction",
    )


class DependencyEdge(BaseModel):
    """Dependency edge between files"""

    source: str = Field(..., description="Source file path")
    target: str = Field(..., description="Target file path")
    relationship: str = Field(..., description="Relationship type (imports, calls, etc.)")


class DependencyGraphResponse(BaseModel):
    """Response model for dependency graph"""

    root_file: str = Field(..., description="Root file path")
    edges: list[DependencyEdge] = Field(..., description="Dependency edges")
    node_count: int = Field(..., description="Total number of nodes")
    edge_count: int = Field(..., description="Total number of edges")
    max_hops: int = Field(..., description="Maximum hops traversed")
    repo_id: str = Field(..., description="Repository UUID")


# ============================================================================
# Blast Radius Models (EP-004)
# ============================================================================


class BlastRadiusRequest(BaseModel):
    """Request model for blast radius computation"""

    repo_id: UUID = Field(..., description="Repository UUID")
    files: list[str] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="List of changed file paths",
        examples=[["src/auth/middleware.py", "src/db/connection.py"]],
    )


class ImpactedFile(BaseModel):
    """Impacted file with metadata"""

    file_path: str = Field(..., description="File path")
    distance: int = Field(..., description="Distance from changed files (hops)")
    acs_score: float | None = Field(None, description="Architectural Criticality Score")
    downstream_services: list[str] = Field(
        default_factory=list,
        description="Downstream services affected",
    )
    test_files: list[str] = Field(
        default_factory=list,
        description="Related test files",
    )


class BlastRadiusResponse(BaseModel):
    """Response model for blast radius computation"""

    changed_files: list[str] = Field(..., description="Original changed files")
    impacted_files: list[ImpactedFile] = Field(..., description="Impacted files sorted by ACS")
    total_impacted: int = Field(..., description="Total number of impacted files")
    affected_services: list[str] = Field(..., description="Affected services")
    repo_id: str = Field(..., description="Repository UUID")


# ============================================================================
# File Models (EP-005)
# ============================================================================


class FileRequest(BaseModel):
    """Request model for file content retrieval"""

    repo_id: UUID = Field(..., description="Repository UUID")
    file_path: str = Field(..., description="File path relative to repository root")


class FileSymbol(BaseModel):
    """Symbol definition in file"""

    name: str = Field(..., description="Symbol name")
    type: str = Field(..., description="Symbol type (function, class, method)")
    start_line: int = Field(..., description="Start line number")
    end_line: int = Field(..., description="End line number")


class FileResponse(BaseModel):
    """Response model for file content"""

    file_path: str = Field(..., description="File path")
    content: str = Field(..., description="File content")
    language: str = Field(..., description="Programming language")
    total_lines: int = Field(..., description="Total line count")
    symbols: list[FileSymbol] = Field(..., description="Parsed symbols")
    imports: list[str] = Field(..., description="Import statements")
    last_modified: str | None = Field(None, description="Last modified timestamp")
    repo_id: str = Field(..., description="Repository UUID")


# ============================================================================
# Commit Diff Models (EP-006)
# ============================================================================


class CommitDiffRequest(BaseModel):
    """Request model for commit diff analysis"""

    repo_id: UUID = Field(..., description="Repository UUID")
    commit_sha: str = Field(
        ...,
        min_length=7,
        max_length=40,
        description="Commit SHA (short or full)",
    )


class ChangedFile(BaseModel):
    """Changed file with impact analysis"""

    file_path: str = Field(..., description="File path")
    change_type: str = Field(..., description="Change type (added, modified, deleted)")
    additions: int = Field(..., description="Lines added")
    deletions: int = Field(..., description="Lines deleted")
    impacted_files: list[str] = Field(
        default_factory=list,
        description="Files impacted by this change",
    )
    test_files: list[str] = Field(
        default_factory=list,
        description="Related test files",
    )


class CommitDiffResponse(BaseModel):
    """Response model for commit diff analysis"""

    commit_sha: str = Field(..., description="Commit SHA")
    author: str | None = Field(None, description="Commit author")
    message: str | None = Field(None, description="Commit message")
    timestamp: str | None = Field(None, description="Commit timestamp")
    changed_files: list[ChangedFile] = Field(..., description="Changed files with impact")
    total_additions: int = Field(..., description="Total lines added")
    total_deletions: int = Field(..., description="Total lines deleted")
    repo_id: str = Field(..., description="Repository UUID")


# ============================================================================
# Health Models (EP-007)
# ============================================================================


class ServiceHealth(BaseModel):
    """Individual service health status"""

    name: str = Field(..., description="Service name")
    status: Literal["healthy", "degraded", "unhealthy", "unknown"] = Field(
        ...,
        description="Health status",
    )
    latency_ms: float | None = Field(None, description="Average latency in milliseconds")
    error_rate: float | None = Field(None, description="Error rate (0.0-1.0)")


class HealthResponse(BaseModel):
    """Response model for health check"""

    status: Literal["healthy", "degraded", "unhealthy"] = Field(
        ...,
        description="Overall health status",
    )
    version: str = Field(..., description="Service version")
    services: dict[str, str] = Field(..., description="Service statuses")
    metrics: dict[str, Any] = Field(..., description="System metrics")
    repos_indexed: int = Field(..., description="Total repositories indexed")
    query_p95_ms: float = Field(..., description="95th percentile query latency")
    index_queue_depth: int = Field(..., description="Indexing queue depth")
    last_error: str | None = Field(None, description="Last error message")


# ============================================================================
# Batch Query Models (EP-008)
# ============================================================================


class SubQuery(BaseModel):
    """Individual sub-query in batch request"""

    query_id: str = Field(..., description="Unique query identifier")
    query_type: Literal[
        "search",
        "stack_trace",
        "dependency_graph",
        "blast_radius",
        "file",
        "commit_diff",
    ] = Field(..., description="Query type")
    params: dict[str, Any] = Field(..., description="Query parameters")

    @field_validator("params")
    @classmethod
    def validate_params(cls, v: dict[str, Any], info) -> dict[str, Any]:
        """Validate params based on query_type"""
        # Basic validation - detailed validation happens in individual handlers
        if not v:
            raise ValueError("params cannot be empty")
        return v


class BatchRequest(BaseModel):
    """Request model for batch queries"""

    queries: list[SubQuery] = Field(
        ...,
        min_length=1,
        max_length=20,
        description="List of sub-queries (max 20)",
    )


class SubQueryResult(BaseModel):
    """Individual sub-query result"""

    query_id: str = Field(..., description="Query identifier")
    success: bool = Field(..., description="Whether query succeeded")
    result: dict[str, Any] | None = Field(None, description="Query result")
    error: str | None = Field(None, description="Error message if failed")
    execution_time_ms: float = Field(..., description="Execution time in milliseconds")


class BatchResponse(BaseModel):
    """Response model for batch queries"""

    results: list[SubQueryResult] = Field(..., description="Sub-query results in order")
    total_queries: int = Field(..., description="Total number of queries")
    successful_queries: int = Field(..., description="Number of successful queries")
    failed_queries: int = Field(..., description="Number of failed queries")
    total_time_ms: float = Field(..., description="Total execution time")


# ============================================================================
# Error Models
# ============================================================================


class ErrorDetail(BaseModel):
    """Error detail model"""

    code: str = Field(..., description="Error code")
    message: str = Field(..., description="Error message")
    details: dict[str, Any] | None = Field(None, description="Additional error details")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Error timestamp")


class ErrorResponse(BaseModel):
    """Standard error response"""

    error: ErrorDetail = Field(..., description="Error details")


# Made with Bob