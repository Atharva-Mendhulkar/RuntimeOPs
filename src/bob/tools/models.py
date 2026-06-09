"""
IBM Bob - Tool Response Models
Pydantic models for agent tool responses
"""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


# ============================================================================
# Tool 1: Semantic Search Models
# ============================================================================


class CodeSearchResult(BaseModel):
    """Individual code search result from semantic search"""

    file_path: str = Field(..., description="File path relative to repository root")
    symbol_name: str = Field(..., description="Symbol name (function, class, etc.)")
    symbol_type: str = Field(..., description="Symbol type (function, class, method)")
    start_line: int = Field(..., description="Start line number")
    end_line: int = Field(..., description="End line number")
    content: str = Field(..., description="Code snippet")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")
    language: str = Field(..., description="Programming language")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata (imports, dependencies, etc.)",
    )


# ============================================================================
# Tool 2: Stack Trace Resolution Models
# ============================================================================


class StackFrame(BaseModel):
    """Resolved stack frame with file path and git blame info"""

    file_path: str | None = Field(None, description="Resolved file path")
    line_number: int | None = Field(None, description="Line number")
    function: str | None = Field(None, description="Function name")
    commit_sha: str | None = Field(None, description="Last commit SHA for this line")
    author: str | None = Field(None, description="Author of last change")
    raw_frame: str = Field(..., description="Original raw frame text")


# ============================================================================
# Tool 3: Dependency Graph Models
# ============================================================================


class DependencyEdge(BaseModel):
    """Dependency edge between files"""

    source: str = Field(..., description="Source file path")
    target: str = Field(..., description="Target file path")
    relationship: str = Field(..., description="Relationship type (imports, calls, etc.)")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional edge metadata",
    )


class DependencyGraph(BaseModel):
    """Dependency graph with nodes and edges"""

    root_file: str = Field(..., description="Root file path")
    edges: list[DependencyEdge] = Field(..., description="Dependency edges")
    nodes: list[str] = Field(..., description="All nodes in the graph")
    node_count: int = Field(..., description="Total number of nodes")
    edge_count: int = Field(..., description="Total number of edges")
    max_hops: int = Field(..., description="Maximum hops traversed")


# ============================================================================
# Tool 4: Blast Radius Models
# ============================================================================


class ImpactedFile(BaseModel):
    """Impacted file with criticality metadata"""

    file_path: str = Field(..., description="File path")
    distance: int = Field(..., description="Distance from changed files (hops)")
    acs_score: float | None = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Architectural Criticality Score",
    )
    downstream_services: list[str] = Field(
        default_factory=list,
        description="Downstream services affected",
    )
    test_files: list[str] = Field(
        default_factory=list,
        description="Related test files",
    )


class BlastRadiusResult(BaseModel):
    """Blast radius computation result"""

    changed_files: list[str] = Field(..., description="Original changed files")
    impacted_files: list[ImpactedFile] = Field(
        ...,
        description="Impacted files sorted by ACS",
    )
    total_impacted: int = Field(..., description="Total number of impacted files")
    affected_services: list[str] = Field(..., description="Affected services")


# ============================================================================
# Tool 5: File Content Models
# ============================================================================


class FileSymbol(BaseModel):
    """Symbol definition in file"""

    name: str = Field(..., description="Symbol name")
    type: str = Field(..., description="Symbol type (function, class, method)")
    start_line: int = Field(..., description="Start line number")
    end_line: int = Field(..., description="End line number")
    docstring: str | None = Field(None, description="Symbol docstring")


class FileContent(BaseModel):
    """File content with parsed metadata"""

    file_path: str = Field(..., description="File path")
    content: str = Field(..., description="File content")
    language: str = Field(..., description="Programming language")
    total_lines: int = Field(..., description="Total line count")
    symbols: list[FileSymbol] = Field(..., description="Parsed symbols")
    imports: list[str] = Field(..., description="Import statements")
    last_modified: datetime | None = Field(None, description="Last modified timestamp")


# ============================================================================
# Tool 6: Commit Diff Models
# ============================================================================


class ChangedFile(BaseModel):
    """Changed file with impact analysis"""

    file_path: str = Field(..., description="File path")
    change_type: Literal["added", "modified", "deleted", "renamed"] = Field(
        ...,
        description="Change type",
    )
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


class CommitDiff(BaseModel):
    """Commit diff with impact analysis"""

    commit_sha: str = Field(..., description="Commit SHA")
    author: str | None = Field(None, description="Commit author")
    message: str | None = Field(None, description="Commit message")
    timestamp: datetime | None = Field(None, description="Commit timestamp")
    changed_files: list[ChangedFile] = Field(..., description="Changed files with impact")
    total_additions: int = Field(..., description="Total lines added")
    total_deletions: int = Field(..., description="Total lines deleted")


# ============================================================================
# Tool 9: Risk Context Models
# ============================================================================


class RiskContext(BaseModel):
    """Risk context for a file"""

    file_path: str = Field(..., description="File path")
    acs_score: float | None = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Architectural Criticality Score",
    )
    downstream_service_count: int = Field(
        ...,
        description="Number of downstream services",
    )
    last_incident_date: datetime | None = Field(
        None,
        description="Date of last incident involving this file",
    )
    incident_count: int = Field(
        default=0,
        description="Total number of incidents involving this file",
    )
    change_frequency: float | None = Field(
        None,
        description="Change frequency (commits per week)",
    )
    risk_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = Field(
        ...,
        description="Computed risk level",
    )


# Made with Bob