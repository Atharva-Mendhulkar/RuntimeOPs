"""
IBM Bob - Neo4j Graph Writer
Writes parsed data to Neo4j graph database
"""

import logging
from typing import Any
from uuid import UUID

from neo4j import GraphDatabase, Session
from neo4j.exceptions import Neo4jError

from bob.config import get_settings
from bob.exceptions import GraphConnectionError, GraphError
from bob.graph.models import (
    BelongsToRelationship,
    CallsRelationship,
    CommitNode,
    ContainsRelationship,
    DefinesRelationship,
    FileNode,
    ImportsRelationship,
    ModifiedRelationship,
    RepositoryNode,
    ServiceNode,
    SymbolNode,
)
from bob.ingestion.analyzer import AnalysisResult, ServiceBoundary
from bob.parsers.base import ParseResult

logger = logging.getLogger(__name__)


class GraphWriter:
    """
    Writes data to Neo4j graph database.
    
    Responsibilities:
    - Create nodes: Repository, File, Symbol, Service, Commit
    - Create relationships: IMPORTS, DEFINES, CALLS, BELONGS_TO, MODIFIED, CONTAINS
    - Use MERGE for idempotency
    - Batch writes (1000 nodes/edges per transaction)
    - Add indexes on repo_id, file_path, symbol.name
    - Implement conflict resolution for incremental updates
    - Graph integrity checks
    """

    def __init__(self) -> None:
        """Initialize the graph writer"""
        self.settings = get_settings()
        self._driver = None
        self._batch_size = 1000

    def __enter__(self) -> "GraphWriter":
        """Context manager entry"""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit"""
        self.close()

    def connect(self) -> None:
        """Connect to Neo4j database"""
        try:
            self._driver = GraphDatabase.driver(
                self.settings.neo4j_uri,
                auth=(self.settings.neo4j_user, self.settings.neo4j_password),
                max_connection_lifetime=3600,
                max_connection_pool_size=50,
                connection_acquisition_timeout=60,
            )
            # Verify connectivity
            self._driver.verify_connectivity()
            logger.info("Connected to Neo4j")
            
            # Create indexes
            self._create_indexes()
        except Exception as e:
            raise GraphConnectionError(
                f"Failed to connect to Neo4j: {str(e)}",
                details={"uri": self.settings.neo4j_uri},
            ) from e

    def close(self) -> None:
        """Close Neo4j connection"""
        if self._driver:
            self._driver.close()
            logger.info("Closed Neo4j connection")

    def _create_indexes(self) -> None:
        """Create indexes for performance"""
        indexes = [
            # Repository indexes
            "CREATE INDEX repo_id_idx IF NOT EXISTS FOR (r:Repository) ON (r.repo_id)",
            "CREATE INDEX repo_github_url_idx IF NOT EXISTS FOR (r:Repository) ON (r.github_url)",
            
            # File indexes
            "CREATE INDEX file_repo_id_idx IF NOT EXISTS FOR (f:File) ON (f.repo_id)",
            "CREATE INDEX file_path_idx IF NOT EXISTS FOR (f:File) ON (f.file_path)",
            "CREATE INDEX file_language_idx IF NOT EXISTS FOR (f:File) ON (f.language)",
            
            # Symbol indexes
            "CREATE INDEX symbol_repo_id_idx IF NOT EXISTS FOR (s:Symbol) ON (s.repo_id)",
            "CREATE INDEX symbol_name_idx IF NOT EXISTS FOR (s:Symbol) ON (s.name)",
            "CREATE INDEX symbol_file_path_idx IF NOT EXISTS FOR (s:Symbol) ON (s.file_path)",
            "CREATE INDEX symbol_type_idx IF NOT EXISTS FOR (s:Symbol) ON (s.symbol_type)",
            
            # Service indexes
            "CREATE INDEX service_repo_id_idx IF NOT EXISTS FOR (s:Service) ON (s.repo_id)",
            "CREATE INDEX service_name_idx IF NOT EXISTS FOR (s:Service) ON (s.name)",
            
            # Commit indexes
            "CREATE INDEX commit_repo_id_idx IF NOT EXISTS FOR (c:Commit) ON (c.repo_id)",
            "CREATE INDEX commit_hash_idx IF NOT EXISTS FOR (c:Commit) ON (c.commit_hash)",
        ]
        
        with self._driver.session() as session:
            for index_query in indexes:
                try:
                    session.run(index_query)
                except Neo4jError as e:
                    logger.warning(f"Failed to create index: {e}")

    def write_repository(
        self,
        repo_id: UUID,
        github_url: str,
        name: str,
        default_branch: str = "main",
    ) -> RepositoryNode:
        """
        Write or update repository node.
        
        Args:
            repo_id: Repository UUID
            github_url: GitHub repository URL
            name: Repository name
            default_branch: Default branch name
            
        Returns:
            Created/updated repository node
        """
        repo_node = RepositoryNode(
            repo_id=repo_id,
            github_url=github_url,
            name=name,
            default_branch=default_branch,
        )
        
        query = """
        MERGE (r:Repository {repo_id: $repo_id})
        SET r += $properties
        RETURN r
        """
        
        with self._driver.session() as session:
            result = session.run(
                query,
                repo_id=str(repo_id),
                properties=repo_node.to_neo4j_properties(),
            )
            result.single()
        
        logger.info(f"Wrote repository node: {name}")
        return repo_node

    def write_parse_results(
        self,
        repo_id: UUID,
        parse_results: list[ParseResult],
        batch_size: int | None = None,
    ) -> dict[str, int]:
        """
        Write parse results to graph in batches.
        
        Args:
            repo_id: Repository UUID
            parse_results: List of parse results
            batch_size: Batch size (default: 1000)
            
        Returns:
            Dictionary with counts of created nodes/edges
        """
        batch_size = batch_size or self._batch_size
        stats = {"files": 0, "symbols": 0, "imports": 0, "defines": 0}
        
        # Batch write files
        file_batches = [
            parse_results[i : i + batch_size]
            for i in range(0, len(parse_results), batch_size)
        ]
        
        for batch in file_batches:
            stats["files"] += self._write_file_batch(repo_id, batch)
        
        # Batch write symbols
        all_symbols = []
        for result in parse_results:
            for symbol in result.symbols:
                all_symbols.append((result, symbol))
        
        symbol_batches = [
            all_symbols[i : i + batch_size]
            for i in range(0, len(all_symbols), batch_size)
        ]
        
        for batch in symbol_batches:
            stats["symbols"] += self._write_symbol_batch(repo_id, batch)
        
        # Batch write imports
        all_imports = []
        for result in parse_results:
            for import_stmt in result.imports:
                all_imports.append((result, import_stmt))
        
        import_batches = [
            all_imports[i : i + batch_size]
            for i in range(0, len(all_imports), batch_size)
        ]
        
        for batch in import_batches:
            stats["imports"] += self._write_import_batch(repo_id, batch)
        
        # Create DEFINES relationships
        stats["defines"] = self._create_defines_relationships(repo_id, parse_results)
        
        logger.info(f"Wrote parse results: {stats}")
        return stats

    def _write_file_batch(
        self,
        repo_id: UUID,
        batch: list[ParseResult],
    ) -> int:
        """Write a batch of file nodes"""
        query = """
        UNWIND $files AS file
        MERGE (f:File {repo_id: file.repo_id, file_path: file.file_path})
        SET f += file.properties
        WITH f
        MATCH (r:Repository {repo_id: f.repo_id})
        MERGE (r)-[:CONTAINS]->(f)
        RETURN count(f) as count
        """
        
        files_data = []
        for result in batch:
            file_node = FileNode(
                repo_id=repo_id,
                file_path=result.file_path,
                language=result.language,
                total_lines=result.total_lines,
                code_lines=result.code_lines,
                comment_lines=result.comment_lines,
                symbols_count=len(result.symbols),
            )
            files_data.append({
                "repo_id": str(repo_id),
                "file_path": result.file_path,
                "properties": file_node.to_neo4j_properties(),
            })
        
        with self._driver.session() as session:
            result = session.run(query, files=files_data)
            count = result.single()["count"]
        
        return count

    def _write_symbol_batch(
        self,
        repo_id: UUID,
        batch: list[tuple[ParseResult, Any]],
    ) -> int:
        """Write a batch of symbol nodes"""
        query = """
        UNWIND $symbols AS symbol
        MERGE (s:Symbol {
            repo_id: symbol.repo_id,
            file_path: symbol.file_path,
            name: symbol.name,
            start_line: symbol.start_line
        })
        SET s += symbol.properties
        RETURN count(s) as count
        """
        
        symbols_data = []
        for result, symbol in batch:
            symbol_node = SymbolNode(
                repo_id=repo_id,
                file_path=result.file_path,
                name=symbol.name,
                symbol_type=symbol.symbol_type.value,
                signature=symbol.signature,
                docstring=symbol.docstring,
                start_line=symbol.start_line,
                end_line=symbol.end_line,
                parent=symbol.parent,
                modifiers=symbol.modifiers or [],
                parameters=symbol.parameters or [],
                return_type=symbol.return_type,
            )
            symbols_data.append({
                "repo_id": str(repo_id),
                "file_path": result.file_path,
                "name": symbol.name,
                "start_line": symbol.start_line,
                "properties": symbol_node.to_neo4j_properties(),
            })
        
        with self._driver.session() as session:
            result = session.run(query, symbols=symbols_data)
            count = result.single()["count"]
        
        return count

    def _write_import_batch(
        self,
        repo_id: UUID,
        batch: list[tuple[ParseResult, Any]],
    ) -> int:
        """Write a batch of import relationships"""
        query = """
        UNWIND $imports AS import
        MATCH (source:File {repo_id: import.repo_id, file_path: import.source_file})
        MERGE (target:File {repo_id: import.repo_id, file_path: import.target_file})
        MERGE (source)-[r:IMPORTS]->(target)
        SET r += import.properties
        RETURN count(r) as count
        """
        
        imports_data = []
        for result, import_stmt in batch:
            # Only create relationships for internal imports
            # External imports would need different handling
            if not import_stmt.is_relative:
                continue
            
            imports_rel = ImportsRelationship(
                source_file=result.file_path,
                target_file=import_stmt.module,  # Simplified - would need resolution
                import_statement=import_stmt.module,
                is_external=False,
                line_number=import_stmt.line_number,
            )
            imports_data.append({
                "repo_id": str(repo_id),
                "source_file": result.file_path,
                "target_file": import_stmt.module,
                "properties": imports_rel.to_neo4j_properties(),
            })
        
        if not imports_data:
            return 0
        
        with self._driver.session() as session:
            result = session.run(query, imports=imports_data)
            count = result.single()["count"]
        
        return count

    def _create_defines_relationships(
        self,
        repo_id: UUID,
        parse_results: list[ParseResult],
    ) -> int:
        """Create DEFINES relationships between files and symbols"""
        query = """
        UNWIND $files AS file_path
        MATCH (f:File {repo_id: $repo_id, file_path: file_path})
        MATCH (s:Symbol {repo_id: $repo_id, file_path: file_path})
        MERGE (f)-[:DEFINES]->(s)
        RETURN count(s) as count
        """
        
        files_with_symbols = [
            r.file_path for r in parse_results if r.symbols
        ]
        
        if not files_with_symbols:
            return 0
            
        total_count = 0
        batch_size = self._batch_size
        
        with self._driver.session() as session:
            for i in range(0, len(files_with_symbols), batch_size):
                batch = files_with_symbols[i:i+batch_size]
                rel_result = session.run(
                    query,
                    repo_id=str(repo_id),
                    files=batch,
                )
                total_count += rel_result.single()["count"]
        
        return total_count

    def write_service_boundaries(
        self,
        repo_id: UUID,
        service_boundaries: list[ServiceBoundary],
    ) -> int:
        """
        Write service boundary nodes and relationships.
        
        Args:
            repo_id: Repository UUID
            service_boundaries: List of detected service boundaries
            
        Returns:
            Number of services written
        """
        query = """
        UNWIND $services AS service
        MERGE (s:Service {repo_id: service.repo_id, name: service.name})
        SET s += service.properties
        WITH s, service
        MATCH (r:Repository {repo_id: service.repo_id})
        MERGE (r)-[:CONTAINS]->(s)
        WITH s, service
        UNWIND service.files AS file_path
        MATCH (f:File {repo_id: service.repo_id, file_path: file_path})
        MERGE (s)-[:CONTAINS]->(f)
        MERGE (f)-[:BELONGS_TO]->(s)
        RETURN count(DISTINCT s) as count
        """
        
        services_data = []
        for boundary in service_boundaries:
            service_node = ServiceNode(
                repo_id=repo_id,
                name=boundary.name,
                service_type=boundary.service_type,
                root_path=boundary.root_path,
                manifest_file=boundary.manifest_file,
                dependencies=boundary.dependencies,
                file_count=len(boundary.files),
            )
            services_data.append({
                "repo_id": str(repo_id),
                "name": boundary.name,
                "files": boundary.files,
                "properties": service_node.to_neo4j_properties(),
            })
        
        with self._driver.session() as session:
            result = session.run(query, services=services_data)
            count = result.single()["count"]
        
        logger.info(f"Wrote {count} service boundaries")
        return count

    def write_analysis_result(
        self,
        repo_id: UUID,
        analysis_result: AnalysisResult,
    ) -> dict[str, int]:
        """
        Write complete analysis result to graph.
        
        Args:
            repo_id: Repository UUID
            analysis_result: Analysis result from StructuralAnalyzer
            
        Returns:
            Dictionary with counts of created elements
        """
        stats = {"services": 0, "call_edges": 0}
        
        # Write service boundaries
        stats["services"] = self.write_service_boundaries(
            repo_id, analysis_result.service_boundaries
        )
        
        # Write call graph edges
        stats["call_edges"] = self._write_call_graph(repo_id, analysis_result)
        
        logger.info(f"Wrote analysis result: {stats}")
        return stats

    def _write_call_graph(
        self,
        repo_id: UUID,
        analysis_result: AnalysisResult,
    ) -> int:
        """Write call graph relationships"""
        query = """
        UNWIND $calls AS call
        MATCH (caller:Symbol {
            repo_id: call.repo_id,
            file_path: call.caller_file,
            name: call.caller_name
        })
        MATCH (callee:Symbol {
            repo_id: call.repo_id,
            file_path: call.callee_file,
            name: call.callee_name
        })
        MERGE (caller)-[r:CALLS]->(callee)
        SET r += call.properties
        RETURN count(r) as count
        """
        
        calls_data = []
        for edge in analysis_result.call_graph.edges(data=True):
            caller_id, callee_id, data = edge
            
            # Parse node IDs (format: "file_path::symbol_name")
            caller_parts = caller_id.split("::")
            callee_parts = callee_id.split("::")
            
            if len(caller_parts) == 2 and len(callee_parts) == 2:
                calls_rel = CallsRelationship(
                    caller=caller_id,
                    callee=callee_id,
                    call_type=data.get("call_type", "direct"),
                )
                calls_data.append({
                    "repo_id": str(repo_id),
                    "caller_file": caller_parts[0],
                    "caller_name": caller_parts[1],
                    "callee_file": callee_parts[0],
                    "callee_name": callee_parts[1],
                    "properties": calls_rel.to_neo4j_properties(),
                })
        
        if not calls_data:
            return 0
        
        # Batch write
        batch_size = self._batch_size
        total_count = 0
        
        for i in range(0, len(calls_data), batch_size):
            batch = calls_data[i : i + batch_size]
            with self._driver.session() as session:
                result = session.run(query, calls=batch)
                total_count += result.single()["count"]
        
        return total_count

    def check_graph_integrity(self, repo_id: UUID) -> dict[str, Any]:
        """
        Check graph integrity for a repository.
        
        Args:
            repo_id: Repository UUID
            
        Returns:
            Dictionary with integrity check results
        """
        checks = {
            "orphaned_symbols": 0,
            "orphaned_files": 0,
            "cycles": [],
            "missing_defines": 0,
        }
        
        with self._driver.session() as session:
            # Check for orphaned symbols (symbols without files)
            result = session.run(
                """
                MATCH (s:Symbol {repo_id: $repo_id})
                WHERE NOT (s)<-[:DEFINES]-(:File)
                RETURN count(s) as count
                """,
                repo_id=str(repo_id),
            )
            checks["orphaned_symbols"] = result.single()["count"]
            
            # Check for orphaned files (files without repository)
            result = session.run(
                """
                MATCH (f:File {repo_id: $repo_id})
                WHERE NOT (f)<-[:CONTAINS]-(:Repository)
                RETURN count(f) as count
                """,
                repo_id=str(repo_id),
            )
            checks["orphaned_files"] = result.single()["count"]
            
            # Check for symbols without DEFINES relationship
            result = session.run(
                """
                MATCH (f:File {repo_id: $repo_id})
                MATCH (s:Symbol {repo_id: $repo_id, file_path: f.file_path})
                WHERE NOT (f)-[:DEFINES]->(s)
                RETURN count(s) as count
                """,
                repo_id=str(repo_id),
            )
            checks["missing_defines"] = result.single()["count"]
        
        logger.info(f"Graph integrity check: {checks}")
        return checks

    def delete_repository(self, repo_id: UUID) -> int:
        """
        Delete all nodes and relationships for a repository.
        
        Args:
            repo_id: Repository UUID
            
        Returns:
            Number of nodes deleted
        """
        query = """
        MATCH (n {repo_id: $repo_id})
        DETACH DELETE n
        RETURN count(n) as count
        """
        
        with self._driver.session() as session:
            result = session.run(query, repo_id=str(repo_id))
            count = result.single()["count"]
        
        logger.info(f"Deleted {count} nodes for repository {repo_id}")
        return count


# Made with Bob