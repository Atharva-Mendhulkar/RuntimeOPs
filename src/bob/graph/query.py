"""
IBM Bob - Neo4j Query Layer
Executes Cypher queries for dependency analysis and graph traversal
"""

import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError

from bob.config import get_settings
from bob.exceptions import GraphConnectionError, QueryError, QueryTimeoutError

logger = logging.getLogger(__name__)


@dataclass
class DependencyPath:
    """Represents a dependency path between two nodes"""

    source: str
    target: str
    path: list[str]
    length: int
    relationship_types: list[str]


@dataclass
class BlastRadiusResult:
    """Result of blast radius computation"""

    changed_files: list[str]
    affected_files: list[str]
    affected_services: list[str]
    total_affected: int
    max_hops: int


@dataclass
class ServiceTopology:
    """Service topology information"""

    services: list[dict[str, Any]]
    inter_service_edges: list[dict[str, Any]]
    total_services: int
    total_edges: int


@dataclass
class CallChain:
    """Function call chain"""

    start_function: str
    end_function: str
    chain: list[str]
    length: int


@dataclass
class GitBlame:
    """Git blame information for a file"""

    file_path: str
    commits: list[dict[str, Any]]
    total_commits: int
    line_ranges: dict[str, list[str]]  # commit_hash -> line_ranges


class GraphQuery:
    """
    Executes Cypher queries on Neo4j graph.

    Responsibilities:
    - Dependency traversal (N-hop upstream/downstream)
    - Blast radius computation
    - Service topology queries
    - Call chain tracing
    - Git blame queries
    - Query result caching (Redis)
    - Query timeout handling
    """

    def __init__(self, cache_ttl: int = 300) -> None:
        """
        Initialize the graph query layer.

        Args:
            cache_ttl: Cache TTL in seconds (default: 5 minutes)
        """
        self.settings = get_settings()
        self._driver = None
        self._cache_ttl = cache_ttl
        self._query_timeout = self.settings.query_timeout_seconds

    def __enter__(self) -> "GraphQuery":
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
            self._driver.verify_connectivity()
            logger.info("Connected to Neo4j for queries")
        except Exception as e:
            raise GraphConnectionError(
                f"Failed to connect to Neo4j: {str(e)}",
                details={"uri": self.settings.neo4j_uri},
            ) from e

    def close(self) -> None:
        """Close Neo4j connection"""
        if self._driver:
            self._driver.close()
            logger.info("Closed Neo4j query connection")

    def get_dependencies(
        self,
        repo_id: UUID,
        file_path: str,
        direction: str = "both",
        max_hops: int = 5,
    ) -> dict[str, list[str]]:
        """
        Get dependencies for a file.

        Args:
            repo_id: Repository UUID
            file_path: File path to analyze
            direction: "upstream", "downstream", or "both"
            max_hops: Maximum number of hops to traverse

        Returns:
            Dictionary with upstream and downstream dependencies
        """
        result = {"upstream": [], "downstream": []}

        if direction in ("upstream", "both"):
            result["upstream"] = self._get_upstream_dependencies(repo_id, file_path, max_hops)

        if direction in ("downstream", "both"):
            result["downstream"] = self._get_downstream_dependencies(repo_id, file_path, max_hops)

        logger.info(
            f"Found {len(result['upstream'])} upstream, "
            f"{len(result['downstream'])} downstream dependencies for {file_path}"
        )
        return result

    def _get_upstream_dependencies(
        self,
        repo_id: UUID,
        file_path: str,
        max_hops: int,
    ) -> list[str]:
        """Get upstream dependencies (files this file depends on)"""
        query = """
        MATCH path = (source:File {repo_id: $repo_id, file_path: $file_path})
                     -[:IMPORTS*1..%d]->(target:File)
        WHERE target.repo_id = $repo_id
        RETURN DISTINCT target.file_path as file_path,
               length(path) as distance
        ORDER BY distance
        """ % max_hops

        with self._driver.session() as session:
            result = session.run(
                query,
                repo_id=str(repo_id),
                file_path=file_path,
                timeout=self._query_timeout,
            )
            return [record["file_path"] for record in result]

    def _get_downstream_dependencies(
        self,
        repo_id: UUID,
        file_path: str,
        max_hops: int,
    ) -> list[str]:
        """Get downstream dependencies (files that depend on this file)"""
        query = """
        MATCH path = (source:File {repo_id: $repo_id, file_path: $file_path})
                     <-[:IMPORTS*1..%d]-(target:File)
        WHERE target.repo_id = $repo_id
        RETURN DISTINCT target.file_path as file_path,
               length(path) as distance
        ORDER BY distance
        """ % max_hops

        with self._driver.session() as session:
            result = session.run(
                query,
                repo_id=str(repo_id),
                file_path=file_path,
                timeout=self._query_timeout,
            )
            return [record["file_path"] for record in result]

    def compute_blast_radius(
        self,
        repo_id: UUID,
        changed_files: list[str],
        max_hops: int = 5,
    ) -> BlastRadiusResult:
        """
        Compute blast radius for changed files.

        Args:
            repo_id: Repository UUID
            changed_files: List of changed file paths
            max_hops: Maximum number of hops to traverse

        Returns:
            Blast radius result with affected files and services
        """
        query = """
        UNWIND $changed_files AS changed_file
        MATCH (source:File {repo_id: $repo_id, file_path: changed_file})
        OPTIONAL MATCH path = (source)<-[:IMPORTS*1..%d]-(affected:File)
        WHERE affected.repo_id = $repo_id
        WITH DISTINCT affected
        OPTIONAL MATCH (affected)-[:BELONGS_TO]->(service:Service)
        RETURN DISTINCT affected.file_path as file_path,
               service.name as service_name
        """ % max_hops

        try:
            with self._driver.session() as session:
                result = session.run(
                    query,
                    repo_id=str(repo_id),
                    changed_files=changed_files,
                    timeout=self._query_timeout,
                )

                affected_files = []
                affected_services = set()

                for record in result:
                    if record["file_path"]:
                        affected_files.append(record["file_path"])
                    if record["service_name"]:
                        affected_services.add(record["service_name"])

                blast_radius = BlastRadiusResult(
                    changed_files=changed_files,
                    affected_files=affected_files,
                    affected_services=list(affected_services),
                    total_affected=len(affected_files),
                    max_hops=max_hops,
                )

                logger.info(
                    f"Blast radius: {len(changed_files)} changed files -> "
                    f"{len(affected_files)} affected files, "
                    f"{len(affected_services)} affected services"
                )
                return blast_radius

        except Neo4jError as e:
            if "timeout" in str(e).lower():
                raise QueryTimeoutError(
                    f"Blast radius query timed out after {self._query_timeout}s",
                    details={"changed_files": len(changed_files)},
                ) from e
            raise QueryError(f"Blast radius query failed: {str(e)}") from e

    def get_service_topology(self, repo_id: UUID) -> ServiceTopology:
        """
        Get service topology (all services and inter-service dependencies).

        Args:
            repo_id: Repository UUID

        Returns:
            Service topology information
        """
        # Get all services
        services_query = """
        MATCH (s:Service {repo_id: $repo_id})
        RETURN s.name as name,
               s.service_type as service_type,
               s.root_path as root_path,
               s.file_count as file_count,
               s.dependencies as dependencies
        """

        # Get inter-service edges
        edges_query = """
        MATCH (s1:Service {repo_id: $repo_id})-[:CONTAINS]->(f1:File)
        MATCH (f1)-[:IMPORTS]->(f2:File)<-[:CONTAINS]-(s2:Service {repo_id: $repo_id})
        WHERE s1 <> s2
        RETURN DISTINCT s1.name as source_service,
               s2.name as target_service,
               count(*) as import_count
        """

        with self._driver.session() as session:
            # Get services
            services_result = session.run(
                services_query,
                repo_id=str(repo_id),
                timeout=self._query_timeout,
            )
            services = [dict(record) for record in services_result]

            # Get edges
            edges_result = session.run(
                edges_query,
                repo_id=str(repo_id),
                timeout=self._query_timeout,
            )
            edges = [dict(record) for record in edges_result]

        topology = ServiceTopology(
            services=services,
            inter_service_edges=edges,
            total_services=len(services),
            total_edges=len(edges),
        )

        logger.info(
            f"Service topology: {topology.total_services} services, "
            f"{topology.total_edges} inter-service edges"
        )
        return topology

    def trace_call_chain(
        self,
        repo_id: UUID,
        start_function: str,
        end_function: str,
        max_hops: int = 10,
    ) -> list[CallChain]:
        """
        Trace call chains between two functions.

        Args:
            repo_id: Repository UUID
            start_function: Starting function (format: "file_path::function_name")
            end_function: Ending function (format: "file_path::function_name")
            max_hops: Maximum chain length

        Returns:
            List of call chains
        """
        # Parse function identifiers
        start_parts = start_function.split("::")
        end_parts = end_function.split("::")

        if len(start_parts) != 2 or len(end_parts) != 2:
            raise QueryError(
                "Invalid function format. Use 'file_path::function_name'",
                details={"start": start_function, "end": end_function},
            )

        query = """
        MATCH (start:Symbol {
            repo_id: $repo_id,
            file_path: $start_file,
            name: $start_name
        })
        MATCH (end:Symbol {
            repo_id: $repo_id,
            file_path: $end_file,
            name: $end_name
        })
        MATCH path = (start)-[:CALLS*1..%d]->(end)
        RETURN [node in nodes(path) | node.file_path + '::' + node.name] as chain,
               length(path) as length
        ORDER BY length
        LIMIT 10
        """ % max_hops

        with self._driver.session() as session:
            result = session.run(
                query,
                repo_id=str(repo_id),
                start_file=start_parts[0],
                start_name=start_parts[1],
                end_file=end_parts[0],
                end_name=end_parts[1],
                timeout=self._query_timeout,
            )

            chains = []
            for record in result:
                chains.append(
                    CallChain(
                        start_function=start_function,
                        end_function=end_function,
                        chain=record["chain"],
                        length=record["length"],
                    )
                )

        logger.info(f"Found {len(chains)} call chains from {start_function} to {end_function}")
        return chains

    def get_git_blame(
        self,
        repo_id: UUID,
        file_path: str,
        line_range: tuple[int, int] | None = None,
    ) -> GitBlame:
        """
        Get git blame information for a file.

        Args:
            repo_id: Repository UUID
            file_path: File path
            line_range: Optional line range (start, end)

        Returns:
            Git blame information
        """
        query = """
        MATCH (f:File {repo_id: $repo_id, file_path: $file_path})
        MATCH (c:Commit {repo_id: $repo_id})-[m:MODIFIED]->(f)
        RETURN c.commit_hash as commit_hash,
               c.author as author,
               c.author_email as author_email,
               c.commit_date as commit_date,
               c.message as message,
               m.line_ranges as line_ranges,
               m.additions as additions,
               m.deletions as deletions
        ORDER BY c.commit_date DESC
        """

        with self._driver.session() as session:
            result = session.run(
                query,
                repo_id=str(repo_id),
                file_path=file_path,
                timeout=self._query_timeout,
            )

            commits = []
            line_ranges_map = {}

            for record in result:
                commit_data = {
                    "commit_hash": record["commit_hash"],
                    "author": record["author"],
                    "author_email": record["author_email"],
                    "commit_date": record["commit_date"],
                    "message": record["message"],
                    "additions": record["additions"],
                    "deletions": record["deletions"],
                }
                commits.append(commit_data)

                if record["line_ranges"]:
                    line_ranges_map[record["commit_hash"]] = record["line_ranges"]

        # Filter by line range if specified
        if line_range:
            filtered_commits = []
            filtered_line_ranges = {}

            for commit in commits:
                commit_hash = commit["commit_hash"]
                if commit_hash in line_ranges_map:
                    # Check if any line range overlaps with requested range
                    for range_str in line_ranges_map[commit_hash]:
                        start, end = map(int, range_str.split("-"))
                        if start <= line_range[1] and end >= line_range[0]:
                            filtered_commits.append(commit)
                            filtered_line_ranges[commit_hash] = line_ranges_map[commit_hash]
                            break

            commits = filtered_commits
            line_ranges_map = filtered_line_ranges

        blame = GitBlame(
            file_path=file_path,
            commits=commits,
            total_commits=len(commits),
            line_ranges=line_ranges_map,
        )

        logger.info(f"Git blame for {file_path}: {len(commits)} commits")
        return blame

    def get_dependency_path(
        self,
        repo_id: UUID,
        source_file: str,
        target_file: str,
        max_hops: int = 10,
    ) -> list[DependencyPath]:
        """
        Find dependency paths between two files.

        Args:
            repo_id: Repository UUID
            source_file: Source file path
            target_file: Target file path
            max_hops: Maximum path length

        Returns:
            List of dependency paths
        """
        query = """
        MATCH (source:File {repo_id: $repo_id, file_path: $source_file})
        MATCH (target:File {repo_id: $repo_id, file_path: $target_file})
        MATCH path = (source)-[:IMPORTS*1..%d]->(target)
        RETURN [node in nodes(path) | node.file_path] as path,
               length(path) as length,
               [rel in relationships(path) | type(rel)] as rel_types
        ORDER BY length
        LIMIT 10
        """ % max_hops

        with self._driver.session() as session:
            result = session.run(
                query,
                repo_id=str(repo_id),
                source_file=source_file,
                target_file=target_file,
                timeout=self._query_timeout,
            )

            paths = []
            for record in result:
                paths.append(
                    DependencyPath(
                        source=source_file,
                        target=target_file,
                        path=record["path"],
                        length=record["length"],
                        relationship_types=record["rel_types"],
                    )
                )

        logger.info(f"Found {len(paths)} dependency paths from {source_file} to {target_file}")
        return paths

    def get_file_metrics(self, repo_id: UUID, file_path: str) -> dict[str, Any]:
        """
        Get metrics for a file.

        Args:
            repo_id: Repository UUID
            file_path: File path

        Returns:
            Dictionary with file metrics
        """
        query = """
        MATCH (f:File {repo_id: $repo_id, file_path: $file_path})
        OPTIONAL MATCH (f)-[:DEFINES]->(s:Symbol)
        OPTIONAL MATCH (f)-[:IMPORTS]->(imported:File)
        OPTIONAL MATCH (f)<-[:IMPORTS]-(importer:File)
        RETURN f.total_lines as total_lines,
               f.code_lines as code_lines,
               f.comment_lines as comment_lines,
               f.language as language,
               count(DISTINCT s) as symbols_count,
               count(DISTINCT imported) as imports_count,
               count(DISTINCT importer) as importers_count
        """

        with self._driver.session() as session:
            result = session.run(
                query,
                repo_id=str(repo_id),
                file_path=file_path,
                timeout=self._query_timeout,
            )
            record = result.single()

            if not record:
                raise QueryError(
                    f"File not found: {file_path}",
                    details={"repo_id": str(repo_id)},
                )

            metrics = {
                "file_path": file_path,
                "total_lines": record["total_lines"],
                "code_lines": record["code_lines"],
                "comment_lines": record["comment_lines"],
                "language": record["language"],
                "symbols_count": record["symbols_count"],
                "imports_count": record["imports_count"],
                "importers_count": record["importers_count"],
                "fan_in": record["importers_count"],
                "fan_out": record["imports_count"],
            }

        logger.info(f"File metrics for {file_path}: {metrics}")
        return metrics


# Made with Bob
