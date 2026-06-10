"""
IBM Bob - Neo4j Graph Models
Pydantic models for graph nodes and relationships
"""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class NodeType(str, Enum):
    """Types of nodes in the graph"""

    REPOSITORY = "Repository"
    FILE = "File"
    SYMBOL = "Symbol"
    SERVICE = "Service"
    COMMIT = "Commit"


class RelationshipType(str, Enum):
    """Types of relationships in the graph"""

    IMPORTS = "IMPORTS"
    DEFINES = "DEFINES"
    CALLS = "CALLS"
    BELONGS_TO = "BELONGS_TO"
    MODIFIED = "MODIFIED"
    CONTAINS = "CONTAINS"


class BaseNode(BaseModel):
    """Base class for all graph nodes"""

    node_id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class RepositoryNode(BaseNode):
    """Repository node in the graph"""

    repo_id: UUID
    github_url: str
    name: str
    default_branch: str = "main"
    last_indexed: datetime | None = None
    total_files: int = 0
    total_symbols: int = 0
    languages: list[str] = Field(default_factory=list)

    def to_neo4j_properties(self) -> dict[str, Any]:
        """Convert to Neo4j properties"""
        return {
            "node_id": self.node_id,
            "repo_id": str(self.repo_id),
            "github_url": self.github_url,
            "name": self.name,
            "default_branch": self.default_branch,
            "last_indexed": self.last_indexed.isoformat() if self.last_indexed else None,
            "total_files": self.total_files,
            "total_symbols": self.total_symbols,
            "languages": self.languages,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class FileNode(BaseNode):
    """File node in the graph"""

    repo_id: UUID
    file_path: str
    language: str
    total_lines: int
    code_lines: int
    comment_lines: int
    symbols_count: int = 0
    last_modified: datetime | None = None
    git_hash: str | None = None

    def to_neo4j_properties(self) -> dict[str, Any]:
        """Convert to Neo4j properties"""
        return {
            "node_id": self.node_id,
            "repo_id": str(self.repo_id),
            "file_path": self.file_path,
            "language": self.language,
            "total_lines": self.total_lines,
            "code_lines": self.code_lines,
            "comment_lines": self.comment_lines,
            "symbols_count": self.symbols_count,
            "last_modified": self.last_modified.isoformat() if self.last_modified else None,
            "git_hash": self.git_hash,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class SymbolNode(BaseNode):
    """Symbol node in the graph (function, class, etc.)"""

    repo_id: UUID
    file_path: str
    name: str
    symbol_type: str  # function, class, method, etc.
    signature: str | None = None
    docstring: str | None = None
    start_line: int
    end_line: int
    parent: str | None = None
    modifiers: list[str] = Field(default_factory=list)
    parameters: list[str] = Field(default_factory=list)
    return_type: str | None = None

    def to_neo4j_properties(self) -> dict[str, Any]:
        """Convert to Neo4j properties"""
        return {
            "node_id": self.node_id,
            "repo_id": str(self.repo_id),
            "file_path": self.file_path,
            "name": self.name,
            "symbol_type": self.symbol_type,
            "signature": self.signature,
            "docstring": self.docstring,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "parent": self.parent,
            "modifiers": self.modifiers,
            "parameters": self.parameters,
            "return_type": self.return_type,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class ServiceNode(BaseNode):
    """Service boundary node in the graph"""

    repo_id: UUID
    name: str
    service_type: str  # npm, go_module, python_package, etc.
    root_path: str
    manifest_file: str
    dependencies: list[str] = Field(default_factory=list)
    file_count: int = 0

    def to_neo4j_properties(self) -> dict[str, Any]:
        """Convert to Neo4j properties"""
        return {
            "node_id": self.node_id,
            "repo_id": str(self.repo_id),
            "name": self.name,
            "service_type": self.service_type,
            "root_path": self.root_path,
            "manifest_file": self.manifest_file,
            "dependencies": self.dependencies,
            "file_count": self.file_count,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class CommitNode(BaseNode):
    """Git commit node in the graph"""

    repo_id: UUID
    commit_hash: str
    author: str
    author_email: str
    commit_date: datetime
    message: str
    files_changed: list[str] = Field(default_factory=list)
    additions: int = 0
    deletions: int = 0

    def to_neo4j_properties(self) -> dict[str, Any]:
        """Convert to Neo4j properties"""
        return {
            "node_id": self.node_id,
            "repo_id": str(self.repo_id),
            "commit_hash": self.commit_hash,
            "author": self.author,
            "author_email": self.author_email,
            "commit_date": self.commit_date.isoformat(),
            "message": self.message,
            "files_changed": self.files_changed,
            "additions": self.additions,
            "deletions": self.deletions,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class BaseRelationship(BaseModel):
    """Base class for all graph relationships"""

    relationship_id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class ImportsRelationship(BaseRelationship):
    """IMPORTS relationship between files"""

    source_file: str
    target_file: str
    import_statement: str
    is_external: bool = False
    line_number: int | None = None

    def to_neo4j_properties(self) -> dict[str, Any]:
        """Convert to Neo4j properties"""
        return {
            "relationship_id": self.relationship_id,
            "import_statement": self.import_statement,
            "is_external": self.is_external,
            "line_number": self.line_number,
            "created_at": self.created_at.isoformat(),
        }


class DefinesRelationship(BaseRelationship):
    """DEFINES relationship between file and symbol"""

    file_path: str
    symbol_name: str

    def to_neo4j_properties(self) -> dict[str, Any]:
        """Convert to Neo4j properties"""
        return {
            "relationship_id": self.relationship_id,
            "created_at": self.created_at.isoformat(),
        }


class CallsRelationship(BaseRelationship):
    """CALLS relationship between symbols"""

    caller: str
    callee: str
    call_type: str = "direct"  # direct, indirect, dynamic
    line_number: int | None = None

    def to_neo4j_properties(self) -> dict[str, Any]:
        """Convert to Neo4j properties"""
        return {
            "relationship_id": self.relationship_id,
            "call_type": self.call_type,
            "line_number": self.line_number,
            "created_at": self.created_at.isoformat(),
        }


class BelongsToRelationship(BaseRelationship):
    """BELONGS_TO relationship between file and service"""

    file_path: str
    service_name: str

    def to_neo4j_properties(self) -> dict[str, Any]:
        """Convert to Neo4j properties"""
        return {
            "relationship_id": self.relationship_id,
            "created_at": self.created_at.isoformat(),
        }


class ModifiedRelationship(BaseRelationship):
    """MODIFIED relationship between commit and file"""

    commit_hash: str
    file_path: str
    change_type: str  # added, modified, deleted
    additions: int = 0
    deletions: int = 0
    line_ranges: list[str] = Field(default_factory=list)  # ["10-20", "30-35"]

    def to_neo4j_properties(self) -> dict[str, Any]:
        """Convert to Neo4j properties"""
        return {
            "relationship_id": self.relationship_id,
            "change_type": self.change_type,
            "additions": self.additions,
            "deletions": self.deletions,
            "line_ranges": self.line_ranges,
            "created_at": self.created_at.isoformat(),
        }


class ContainsRelationship(BaseRelationship):
    """CONTAINS relationship between repository and file/service"""

    container: str  # repo_id or service_name
    contained: str  # file_path or service_name

    def to_neo4j_properties(self) -> dict[str, Any]:
        """Convert to Neo4j properties"""
        return {
            "relationship_id": self.relationship_id,
            "created_at": self.created_at.isoformat(),
        }


# Made with Bob
