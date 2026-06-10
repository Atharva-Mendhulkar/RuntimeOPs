"""
Unit tests for ingestion components
"""

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from bob.ingestion.analyzer import StructuralAnalyzer
from bob.ingestion.orchestrator import IngestionStatus, IngestOrchestrator
from bob.parsers.base import (
    CodeSymbol,
    ImportStatement,
    ParseResult,
    SymbolType,
)


class TestStructuralAnalyzer:
    """Tests for StructuralAnalyzer"""

    def setup_method(self):
        """Setup test fixtures"""
        self.analyzer = StructuralAnalyzer()

    def test_initialization(self):
        """Test analyzer initialization"""
        assert self.analyzer.dependency_graph is not None
        assert self.analyzer.call_graph is not None
        assert isinstance(self.analyzer.service_boundaries, list)
        assert isinstance(self.analyzer.file_to_service, dict)

    def test_detect_service_boundaries_npm(self, tmp_path):
        """Test detecting npm service boundaries"""
        # Create a package.json
        package_json = tmp_path / "package.json"
        package_json.write_text('{"name": "test-service", "dependencies": {"express": "^4.0.0"}}')

        boundaries = self.analyzer._detect_service_boundaries(tmp_path)

        assert len(boundaries) > 0
        npm_boundary = [b for b in boundaries if b.service_type == "npm"][0]
        assert npm_boundary.name == "test-service"
        assert "express" in npm_boundary.dependencies

    def test_detect_service_boundaries_python(self, tmp_path):
        """Test detecting Python service boundaries"""
        # Create a setup.py
        setup_py = tmp_path / "setup.py"
        setup_py.write_text('from setuptools import setup\nsetup(name="test-package")')

        boundaries = self.analyzer._detect_service_boundaries(tmp_path)

        assert len(boundaries) > 0
        python_boundary = [b for b in boundaries if b.service_type == "python_package"][0]
        assert python_boundary.name == tmp_path.name

    def test_build_dependency_graph(self, tmp_path):
        """Test building dependency graph"""
        # Create mock parse results
        parse_results = [
            ParseResult(
                file_path="src/main.py",
                language="python",
                symbols=[
                    CodeSymbol(
                        name="main",
                        symbol_type=SymbolType.FUNCTION,
                        file_path="src/main.py",
                        start_line=1,
                        end_line=5,
                        start_byte=0,
                        end_byte=100,
                    )
                ],
                imports=[
                    ImportStatement(
                        module="utils",
                        imported_names=["helper"],
                        is_relative=True,
                        line_number=1,
                    )
                ],
                exports=[],
                total_lines=10,
                code_lines=8,
                comment_lines=2,
                parse_errors=[],
                success=True,
            ),
            ParseResult(
                file_path="src/utils.py",
                language="python",
                symbols=[
                    CodeSymbol(
                        name="helper",
                        symbol_type=SymbolType.FUNCTION,
                        file_path="src/utils.py",
                        start_line=1,
                        end_line=3,
                        start_byte=0,
                        end_byte=50,
                    )
                ],
                imports=[],
                exports=[],
                total_lines=5,
                code_lines=4,
                comment_lines=1,
                parse_errors=[],
                success=True,
            ),
        ]

        self.analyzer._build_dependency_graph(tmp_path, parse_results)

        # Check nodes were added
        assert self.analyzer.dependency_graph.number_of_nodes() == 2
        assert self.analyzer.dependency_graph.has_node("src/main.py")
        assert self.analyzer.dependency_graph.has_node("src/utils.py")

    def test_compute_blast_radius(self):
        """Test blast radius computation"""
        # Build a simple dependency graph
        self.analyzer.dependency_graph.add_edge("file1.py", "file2.py")
        self.analyzer.dependency_graph.add_edge("file2.py", "file3.py")
        self.analyzer.dependency_graph.add_edge("file1.py", "file4.py")

        # Compute blast radius for file1.py
        affected = self.analyzer.compute_blast_radius(["file1.py"], max_hops=5)

        # Should include file1 and all its descendants
        assert "file1.py" in affected
        assert "file2.py" in affected
        assert "file3.py" in affected
        assert "file4.py" in affected

    def test_compute_architectural_criticality_score(self):
        """Test ACS computation"""
        # Build a graph where file2 is central
        self.analyzer.dependency_graph.add_edge("file1.py", "file2.py")
        self.analyzer.dependency_graph.add_edge("file3.py", "file2.py")
        self.analyzer.dependency_graph.add_edge("file2.py", "file4.py")
        self.analyzer.dependency_graph.add_edge("file2.py", "file5.py")

        # file2 should have high ACS (high in-degree and out-degree)
        acs = self.analyzer.compute_architectural_criticality_score("file2.py")

        assert acs > 0.0
        assert acs <= 1.0

        # file1 should have lower ACS (only out-degree)
        acs_file1 = self.analyzer.compute_architectural_criticality_score("file1.py")
        assert acs_file1 < acs


class TestIngestOrchestrator:
    """Tests for IngestOrchestrator"""

    def setup_method(self):
        """Setup test fixtures"""
        self.orchestrator = IngestOrchestrator()

    def test_initialization(self):
        """Test orchestrator initialization"""
        assert len(self.orchestrator._parsers) > 0
        assert "python" in self.orchestrator._parsers
        assert "typescript" in self.orchestrator._parsers
        assert "javascript" in self.orchestrator._parsers
        assert "go" in self.orchestrator._parsers
        assert "java" in self.orchestrator._parsers

    def test_get_parser_for_file(self):
        """Test parser selection"""
        python_parser = self.orchestrator._get_parser_for_file(Path("test.py"))
        assert python_parser is not None
        assert python_parser.language_name == "python"

        ts_parser = self.orchestrator._get_parser_for_file(Path("test.ts"))
        assert ts_parser is not None
        assert ts_parser.language_name == "typescript"

        js_parser = self.orchestrator._get_parser_for_file(Path("test.js"))
        assert js_parser is not None
        assert js_parser.language_name == "javascript"

        # Unknown extension
        unknown_parser = self.orchestrator._get_parser_for_file(Path("test.xyz"))
        assert unknown_parser is None

    def test_should_parse_file(self):
        """Test file filtering"""
        # Should parse
        assert self.orchestrator._should_parse_file(Path("src/main.py"))
        assert self.orchestrator._should_parse_file(Path("lib/utils.ts"))

        # Should skip
        assert not self.orchestrator._should_parse_file(Path("node_modules/package/index.js"))
        assert not self.orchestrator._should_parse_file(Path("venv/lib/python3.11/site.py"))
        assert not self.orchestrator._should_parse_file(Path("tests/test_main.py"))
        assert not self.orchestrator._should_parse_file(Path(".git/config"))

    @patch("bob.ingestion.orchestrator.RepositoryFetcher")
    def test_fetch_repository(self, mock_fetcher_class):
        """Test repository fetching"""
        # Mock the fetcher
        mock_fetcher = MagicMock()
        mock_metadata = Mock()
        mock_metadata.total_lines = 1000
        mock_fetcher.clone_repository.return_value = (Path("/tmp/repo"), mock_metadata)
        mock_fetcher_class.return_value.__enter__.return_value = mock_fetcher

        repo_path, metadata = self.orchestrator._fetch_repository(
            "https://github.com/test/repo", 12345, None
        )

        assert repo_path == Path("/tmp/repo")
        assert metadata.total_lines == 1000
        mock_fetcher.clone_repository.assert_called_once()

    def test_save_and_get_checkpoint(self):
        """Test checkpoint management"""
        job_id = "test_job_123"

        # Save checkpoint
        self.orchestrator._save_checkpoint(
            job_id,
            IngestionStatus.PARSING,
            repo_path=Path("/tmp/repo"),
        )

        # Verify checkpoint exists
        assert job_id in self.orchestrator._checkpoints
        checkpoint = self.orchestrator._checkpoints[job_id]
        assert checkpoint.status == IngestionStatus.PARSING
        assert checkpoint.repo_path == Path("/tmp/repo")

        # Get progress
        progress = self.orchestrator.get_progress(job_id)
        assert progress is not None
        assert progress.job_id == job_id
        assert progress.status == IngestionStatus.PARSING


class TestIngestionIntegration:
    """Integration tests for ingestion pipeline"""

    def test_end_to_end_mock(self, tmp_path):
        """Test end-to-end ingestion with mocked components"""
        # Create a simple Python file
        test_file = tmp_path / "test.py"
        test_file.write_text('''
def hello():
    """Say hello"""
    return "Hello, World!"
''')

        # This would be a full integration test
        # For now, just verify the file exists
        assert test_file.exists()

        # In a real test, we would:
        # 1. Mock RepositoryFetcher to return tmp_path
        # 2. Run orchestrator.ingest_repository()
        # 3. Verify all stages completed
        # 4. Check parse results, analysis, embeddings, etc.


# Made with Bob
