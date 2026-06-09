"""
IBM Bob - Structural Analyzer
Builds file-level dependency graphs and detects service boundaries
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import networkx as nx

from bob.parsers.base import ImportStatement, ParseResult

logger = logging.getLogger(__name__)


@dataclass
class ServiceBoundary:
    """Represents a detected service boundary"""

    name: str
    root_path: str
    service_type: str  # "npm", "go_module", "python_package", "maven", etc.
    manifest_file: str  # package.json, go.mod, setup.py, pom.xml
    dependencies: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)


@dataclass
class DependencyEdge:
    """Represents a dependency edge between files"""

    source_file: str
    target_file: str
    import_statement: str
    edge_type: str  # "import", "require", "include"
    is_external: bool = False  # External package vs internal file


@dataclass
class CallGraphNode:
    """Represents a function/method in the call graph"""

    name: str
    file_path: str
    line_number: int
    symbol_type: str  # "function", "method", "class"
    parent: str | None = None


@dataclass
class AnalysisResult:
    """Result of structural analysis"""

    dependency_graph: nx.DiGraph
    service_boundaries: list[ServiceBoundary]
    call_graph: nx.DiGraph
    file_to_service: dict[str, str]  # Map file paths to service names
    external_dependencies: set[str]
    total_files: int
    total_edges: int


class StructuralAnalyzer:
    """
    Analyzes repository structure and builds dependency graphs.
    
    Responsibilities:
    - Build file-level dependency graph from imports
    - Detect service boundaries (package.json, go.mod, setup.py, pom.xml)
    - Generate call graph (function-level)
    - Use NetworkX for graph algorithms
    """

    def __init__(self) -> None:
        """Initialize the structural analyzer"""
        self.dependency_graph = nx.DiGraph()
        self.call_graph = nx.DiGraph()
        self.service_boundaries: list[ServiceBoundary] = []
        self.file_to_service: dict[str, str] = {}
        self.external_dependencies: set[str] = set()

    def analyze(
        self,
        repo_path: Path,
        parse_results: list[ParseResult],
    ) -> AnalysisResult:
        """
        Perform structural analysis on parsed repository.
        
        Args:
            repo_path: Path to repository root
            parse_results: List of parse results from language parsers
            
        Returns:
            Analysis result with graphs and service boundaries
        """
        logger.info(f"Starting structural analysis for {repo_path}")

        # Detect service boundaries first
        self.service_boundaries = self._detect_service_boundaries(repo_path)
        logger.info(f"Detected {len(self.service_boundaries)} service boundaries")

        # Map files to services
        self._map_files_to_services(parse_results)

        # Build dependency graph from imports
        self._build_dependency_graph(repo_path, parse_results)
        logger.info(
            f"Built dependency graph: {self.dependency_graph.number_of_nodes()} nodes, "
            f"{self.dependency_graph.number_of_edges()} edges"
        )

        # Build call graph from symbols
        self._build_call_graph(parse_results)
        logger.info(
            f"Built call graph: {self.call_graph.number_of_nodes()} nodes, "
            f"{self.call_graph.number_of_edges()} edges"
        )

        return AnalysisResult(
            dependency_graph=self.dependency_graph,
            service_boundaries=self.service_boundaries,
            call_graph=self.call_graph,
            file_to_service=self.file_to_service,
            external_dependencies=self.external_dependencies,
            total_files=len(parse_results),
            total_edges=self.dependency_graph.number_of_edges(),
        )

    def _detect_service_boundaries(self, repo_path: Path) -> list[ServiceBoundary]:
        """
        Detect service boundaries by finding manifest files.
        
        Args:
            repo_path: Path to repository root
            
        Returns:
            List of detected service boundaries
        """
        boundaries = []

        # Manifest file patterns and their types
        manifest_patterns = {
            "package.json": "npm",
            "go.mod": "go_module",
            "setup.py": "python_package",
            "pyproject.toml": "python_package",
            "pom.xml": "maven",
            "build.gradle": "gradle",
            "Cargo.toml": "rust_crate",
        }

        for pattern, service_type in manifest_patterns.items():
            for manifest_file in repo_path.rglob(pattern):
                # Skip node_modules and other dependency directories
                if self._should_skip_directory(manifest_file):
                    continue

                service_name = manifest_file.parent.name
                root_path = str(manifest_file.parent.relative_to(repo_path))

                # Extract dependencies from manifest
                dependencies = self._extract_dependencies_from_manifest(
                    manifest_file, service_type
                )

                # Find all files in this service
                service_files = self._find_service_files(manifest_file.parent, repo_path)

                boundary = ServiceBoundary(
                    name=service_name,
                    root_path=root_path,
                    service_type=service_type,
                    manifest_file=str(manifest_file.relative_to(repo_path)),
                    dependencies=dependencies,
                    files=service_files,
                )
                boundaries.append(boundary)
                logger.debug(
                    f"Detected {service_type} service: {service_name} "
                    f"at {root_path} with {len(service_files)} files"
                )

        return boundaries

    def _should_skip_directory(self, path: Path) -> bool:
        """Check if directory should be skipped"""
        skip_dirs = {
            "node_modules",
            "venv",
            "env",
            ".venv",
            "vendor",
            "target",
            "build",
            "dist",
            ".git",
        }
        return any(part in skip_dirs for part in path.parts)

    def _extract_dependencies_from_manifest(
        self,
        manifest_file: Path,
        service_type: str,
    ) -> list[str]:
        """Extract dependencies from manifest file"""
        dependencies = []

        try:
            if service_type == "npm" and manifest_file.name == "package.json":
                with open(manifest_file, "r") as f:
                    data = json.load(f)
                    deps = data.get("dependencies", {})
                    dev_deps = data.get("devDependencies", {})
                    dependencies.extend(deps.keys())
                    dependencies.extend(dev_deps.keys())

            elif service_type == "go_module" and manifest_file.name == "go.mod":
                with open(manifest_file, "r") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("require"):
                            # Simple parsing - could be improved
                            parts = line.split()
                            if len(parts) >= 2:
                                dependencies.append(parts[1])

            elif service_type == "python_package":
                if manifest_file.name == "pyproject.toml":
                    # Would need toml parser - skip for now
                    pass
                elif manifest_file.name == "setup.py":
                    # Would need to parse Python - skip for now
                    pass

            elif service_type == "maven" and manifest_file.name == "pom.xml":
                # Would need XML parser - skip for now
                pass

        except Exception as e:
            logger.warning(f"Failed to extract dependencies from {manifest_file}: {e}")

        return dependencies

    def _find_service_files(self, service_root: Path, repo_path: Path) -> list[str]:
        """Find all source files belonging to a service"""
        files = []
        source_extensions = {".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".java"}

        for file_path in service_root.rglob("*"):
            if file_path.is_file() and file_path.suffix in source_extensions:
                if not self._should_skip_directory(file_path):
                    rel_path = str(file_path.relative_to(repo_path))
                    files.append(rel_path)

        return files

    def _map_files_to_services(self, parse_results: list[ParseResult]) -> None:
        """Map each file to its service boundary"""
        for result in parse_results:
            file_path = result.file_path
            
            # Find which service this file belongs to
            for boundary in self.service_boundaries:
                if file_path in boundary.files:
                    self.file_to_service[file_path] = boundary.name
                    break
            
            # If no service found, mark as root
            if file_path not in self.file_to_service:
                self.file_to_service[file_path] = "root"

    def _build_dependency_graph(
        self,
        repo_path: Path,
        parse_results: list[ParseResult],
    ) -> None:
        """Build file-level dependency graph from imports"""
        # Add all files as nodes
        for result in parse_results:
            self.dependency_graph.add_node(
                result.file_path,
                language=result.language,
                service=self.file_to_service.get(result.file_path, "root"),
                symbols_count=len(result.symbols),
            )

        # Add edges from imports
        for result in parse_results:
            source_file = result.file_path
            
            for import_stmt in result.imports:
                target_file = self._resolve_import_to_file(
                    import_stmt, source_file, repo_path, result.language
                )
                
                if target_file:
                    # Internal dependency
                    if target_file in [r.file_path for r in parse_results]:
                        self.dependency_graph.add_edge(
                            source_file,
                            target_file,
                            import_statement=import_stmt.module,
                            edge_type="import",
                            is_external=False,
                        )
                    else:
                        # External dependency
                        self.external_dependencies.add(import_stmt.module)
                        # Optionally add external node
                        if not self.dependency_graph.has_node(import_stmt.module):
                            self.dependency_graph.add_node(
                                import_stmt.module,
                                language="external",
                                service="external",
                                is_external=True,
                            )
                        self.dependency_graph.add_edge(
                            source_file,
                            import_stmt.module,
                            import_statement=import_stmt.module,
                            edge_type="import",
                            is_external=True,
                        )

    def _resolve_import_to_file(
        self,
        import_stmt: ImportStatement,
        source_file: str,
        repo_path: Path,
        language: str,
    ) -> str | None:
        """
        Resolve an import statement to a file path.
        
        This is a simplified implementation. A production version would need
        to handle language-specific module resolution rules.
        """
        module = import_stmt.module

        # Handle relative imports
        if import_stmt.is_relative:
            source_dir = Path(source_file).parent
            
            if language == "python":
                # Python relative imports
                module_path = module.replace(".", "/")
                potential_files = [
                    source_dir / f"{module_path}.py",
                    source_dir / module_path / "__init__.py",
                ]
            elif language in ("typescript", "javascript"):
                # JS/TS relative imports
                potential_files = [
                    source_dir / f"{module}.ts",
                    source_dir / f"{module}.tsx",
                    source_dir / f"{module}.js",
                    source_dir / f"{module}.jsx",
                    source_dir / module / "index.ts",
                    source_dir / module / "index.js",
                ]
            else:
                return None
            
            for potential_file in potential_files:
                if potential_file.exists():
                    try:
                        return str(potential_file.relative_to(repo_path))
                    except ValueError:
                        pass
        
        # For absolute imports, would need more sophisticated resolution
        # This is a placeholder - production would use language-specific resolvers
        return None

    def _build_call_graph(self, parse_results: list[ParseResult]) -> None:
        """Build function-level call graph"""
        # Add all functions/methods as nodes
        for result in parse_results:
            for symbol in result.symbols:
                if symbol.symbol_type.value in ("function", "method"):
                    node_id = f"{result.file_path}::{symbol.name}"
                    self.call_graph.add_node(
                        node_id,
                        name=symbol.name,
                        file_path=result.file_path,
                        line_number=symbol.start_line,
                        symbol_type=symbol.symbol_type.value,
                        parent=symbol.parent,
                    )
        
        # Build edges by analyzing function bodies for calls
        # This is a simplified version - production would use more sophisticated analysis
        for result in parse_results:
            for symbol in result.symbols:
                if symbol.symbol_type.value in ("function", "method") and symbol.body:
                    source_node = f"{result.file_path}::{symbol.name}"
                    
                    # Look for function calls in the body
                    # This is a naive approach - would need proper AST analysis
                    for other_result in parse_results:
                        for other_symbol in other_result.symbols:
                            if other_symbol.symbol_type.value in ("function", "method"):
                                if other_symbol.name in symbol.body:
                                    target_node = f"{other_result.file_path}::{other_symbol.name}"
                                    if source_node != target_node:
                                        self.call_graph.add_edge(
                                            source_node,
                                            target_node,
                                            call_type="direct",
                                        )

    def compute_blast_radius(
        self,
        changed_files: list[str],
        max_hops: int = 5,
    ) -> set[str]:
        """
        Compute blast radius for changed files.
        
        Args:
            changed_files: List of changed file paths
            max_hops: Maximum number of hops to traverse
            
        Returns:
            Set of affected file paths
        """
        affected = set(changed_files)
        
        for file_path in changed_files:
            if file_path not in self.dependency_graph:
                continue
            
            # Get all descendants (files that depend on this file)
            try:
                descendants = nx.descendants(self.dependency_graph, file_path)
                
                # Limit by hop distance
                for descendant in descendants:
                    try:
                        path_length = nx.shortest_path_length(
                            self.dependency_graph, file_path, descendant
                        )
                        if path_length <= max_hops:
                            affected.add(descendant)
                    except nx.NetworkXNoPath:
                        pass
            except nx.NetworkXError:
                pass
        
        return affected

    def get_file_dependencies(
        self,
        file_path: str,
        direction: str = "both",
        max_hops: int = 5,
    ) -> dict[str, Any]:
        """
        Get dependencies for a file.
        
        Args:
            file_path: File path to analyze
            direction: "upstream", "downstream", or "both"
            max_hops: Maximum number of hops to traverse
            
        Returns:
            Dictionary with upstream and downstream dependencies
        """
        result = {"upstream": [], "downstream": []}
        
        if file_path not in self.dependency_graph:
            return result
        
        if direction in ("upstream", "both"):
            # Files this file depends on
            try:
                ancestors = nx.ancestors(self.dependency_graph, file_path)
                for ancestor in ancestors:
                    try:
                        path_length = nx.shortest_path_length(
                            self.dependency_graph, ancestor, file_path
                        )
                        if path_length <= max_hops:
                            result["upstream"].append(ancestor)
                    except nx.NetworkXNoPath:
                        pass
            except nx.NetworkXError:
                pass
        
        if direction in ("downstream", "both"):
            # Files that depend on this file
            try:
                descendants = nx.descendants(self.dependency_graph, file_path)
                for descendant in descendants:
                    try:
                        path_length = nx.shortest_path_length(
                            self.dependency_graph, file_path, descendant
                        )
                        if path_length <= max_hops:
                            result["downstream"].append(descendant)
                    except nx.NetworkXNoPath:
                        pass
            except nx.NetworkXError:
                pass
        
        return result

    def compute_architectural_criticality_score(self, file_path: str) -> float:
        """
        Compute Architectural Criticality Score (ACS) for a file.
        
        Based on:
        - In-degree (how many files depend on this)
        - Out-degree (how many files this depends on)
        - Betweenness centrality
        
        Args:
            file_path: File path to analyze
            
        Returns:
            ACS score between 0.0 and 1.0
        """
        if file_path not in self.dependency_graph:
            return 0.0
        
        # Get in-degree (files that depend on this)
        in_degree = self.dependency_graph.in_degree(file_path)
        
        # Get out-degree (files this depends on)
        out_degree = self.dependency_graph.out_degree(file_path)
        
        # Compute betweenness centrality (how often this file is on shortest paths)
        try:
            betweenness = nx.betweenness_centrality(self.dependency_graph)
            betweenness_score = betweenness.get(file_path, 0.0)
        except:
            betweenness_score = 0.0
        
        # Normalize and combine scores
        max_degree = max(
            max(dict(self.dependency_graph.in_degree()).values(), default=1),
            max(dict(self.dependency_graph.out_degree()).values(), default=1),
        )
        
        normalized_in = in_degree / max_degree if max_degree > 0 else 0
        normalized_out = out_degree / max_degree if max_degree > 0 else 0
        
        # Weighted combination (in-degree is more important)
        acs = (0.5 * normalized_in + 0.2 * normalized_out + 0.3 * betweenness_score)
        
        return min(acs, 1.0)


# Made with Bob