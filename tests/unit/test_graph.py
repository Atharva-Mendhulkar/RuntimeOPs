"""
IBM Bob - Unit Tests for Graph Components
Tests for Neo4j graph models, writer, and query layer
"""

from datetime import datetime
from unittest.mock import MagicMock, Mock, patch
from uuid import UUID, uuid4

import pytest

from bob.graph.models import (
    CallsRelationship,
    CommitNode,
    FileNode,
    ImportsRelationship,
    RepositoryNode,
    ServiceNode,
    SymbolNode,
)
from bob.graph.query import BlastRadiusResult, CallChain, DependencyPath, ServiceTopology
from bob.graph.writer import GraphWriter


class TestGraphModels:
    """Unit tests for graph models"""

    def test_repository_node_creation(self):
        """Test repository node creation"""
        repo_id = uuid4()
        repo = RepositoryNode(
            repo_id=repo_id,
            github_url="https://github.com/test/repo",
            name="test-repo",
            default_branch="main",
        )
        
        assert repo.repo_id == repo_id
        assert repo.github_url == "https://github.com/test/repo"
        assert repo.name == "test-repo"
        assert repo.default_branch == "main"

    def test_repository_node_to_neo4j_properties(self):
        """Test repository node conversion to Neo4j properties"""
        repo_id = uuid4()
        repo = RepositoryNode(
            repo_id=repo_id,
            github_url="https://github.com/test/repo",
            name="test-repo",
        )
        
        props = repo.to_neo4j_properties()
        assert props["repo_id"] == str(repo_id)
        assert props["github_url"] == "https://github.com/test/repo"
        assert props["name"] == "test-repo"
        assert "created_at" in props
        assert "updated_at" in props

    def test_file_node_creation(self):
        """Test file node creation"""
        repo_id = uuid4()
        file_node = FileNode(
            repo_id=repo_id,
            file_path="src/main.py",
            language="python",
            total_lines=100,
            code_lines=80,
            comment_lines=15,
            symbols_count=5,
        )
        
        assert file_node.repo_id == repo_id
        assert file_node.file_path == "src/main.py"
        assert file_node.language == "python"
        assert file_node.total_lines == 100
        assert file_node.code_lines == 80

    def test_symbol_node_creation(self):
        """Test symbol node creation"""
        repo_id = uuid4()
        symbol = SymbolNode(
            repo_id=repo_id,
            file_path="src/main.py",
            name="calculate_total",
            symbol_type="function",
            start_line=10,
            end_line=20,
            signature="def calculate_total(items: list) -> float",
            parameters=["items"],
            return_type="float",
        )
        
        assert symbol.name == "calculate_total"
        assert symbol.symbol_type == "function"
        assert symbol.start_line == 10
        assert symbol.end_line == 20
        assert len(symbol.parameters) == 1

    def test_service_node_creation(self):
        """Test service node creation"""
        repo_id = uuid4()
        service = ServiceNode(
            repo_id=repo_id,
            name="payment-service",
            service_type="npm",
            root_path="services/payment",
            manifest_file="services/payment/package.json",
            dependencies=["express", "axios"],
            file_count=25,
        )
        
        assert service.name == "payment-service"
        assert service.service_type == "npm"
        assert len(service.dependencies) == 2
        assert service.file_count == 25

    def test_commit_node_creation(self):
        """Test commit node creation"""
        repo_id = uuid4()
        commit = CommitNode(
            repo_id=repo_id,
            commit_hash="abc123",
            author="John Doe",
            author_email="john@example.com",
            commit_date=datetime.utcnow(),
            message="Fix bug in payment processing",
            files_changed=["src/payment.py", "tests/test_payment.py"],
            additions=15,
            deletions=5,
        )
        
        assert commit.commit_hash == "abc123"
        assert commit.author == "John Doe"
        assert len(commit.files_changed) == 2
        assert commit.additions == 15

    def test_imports_relationship_creation(self):
        """Test imports relationship creation"""
        rel = ImportsRelationship(
            source_file="src/main.py",
            target_file="src/utils.py",
            import_statement="from utils import helper",
            is_external=False,
            line_number=5,
        )
        
        assert rel.source_file == "src/main.py"
        assert rel.target_file == "src/utils.py"
        assert rel.is_external is False
        assert rel.line_number == 5

    def test_calls_relationship_creation(self):
        """Test calls relationship creation"""
        rel = CallsRelationship(
            caller="src/main.py::main",
            callee="src/utils.py::helper",
            call_type="direct",
            line_number=15,
        )
        
        assert rel.caller == "src/main.py::main"
        assert rel.callee == "src/utils.py::helper"
        assert rel.call_type == "direct"


class TestGraphWriter:
    """Unit tests for GraphWriter"""

    @pytest.fixture
    def mock_driver(self):
        """Mock Neo4j driver"""
        with patch("bob.graph.writer.GraphDatabase.driver") as mock:
            driver = MagicMock()
            driver.verify_connectivity.return_value = None
            
            # Mock session
            session = MagicMock()
            session.run.return_value = MagicMock(single=lambda: {"count": 1})
            driver.session.return_value.__enter__.return_value = session
            driver.session.return_value.__exit__.return_value = None
            
            mock.return_value = driver
            yield driver

    def test_writer_initialization(self, mock_driver):
        """Test writer initialization"""
        writer = GraphWriter()
        writer.connect()
        
        assert writer._driver is not None
        mock_driver.verify_connectivity.assert_called_once()

    def test_write_repository(self, mock_driver):
        """Test write repository"""
        writer = GraphWriter()
        writer.connect()
        
        repo_id = uuid4()
        repo_node = writer.write_repository(
            repo_id=repo_id,
            github_url="https://github.com/test/repo",
            name="test-repo",
        )
        
        assert repo_node.repo_id == repo_id
        assert repo_node.github_url == "https://github.com/test/repo"

    def test_write_parse_results_batch(self, mock_driver):
        """Test batch write of parse results"""
        writer = GraphWriter()
        writer.connect()
        
        # Mock parse results
        from bob.parsers.base import ParseResult, CodeSymbol, SymbolType
        
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
                        end_line=10,
                        start_byte=0,
                        end_byte=100,
                    )
                ],
                imports=[],
                exports=[],
                total_lines=10,
                code_lines=8,
                comment_lines=2,
                parse_errors=[],
                success=True,
            )
        ]
        
        repo_id = uuid4()
        stats = writer.write_parse_results(repo_id, parse_results)
        
        assert "files" in stats
        assert "symbols" in stats
        assert stats["files"] >= 0

    def test_check_graph_integrity(self, mock_driver):
        """Test graph integrity check"""
        writer = GraphWriter()
        writer.connect()
        
        repo_id = uuid4()
        checks = writer.check_graph_integrity(repo_id)
        
        assert "orphaned_symbols" in checks
        assert "orphaned_files" in checks
        assert "cycles" in checks
        assert "missing_defines" in checks


class TestGraphQuery:
    """Unit tests for GraphQuery"""

    @pytest.fixture
    def mock_driver(self):
        """Mock Neo4j driver"""
        with patch("bob.graph.query.GraphDatabase.driver") as mock:
            driver = MagicMock()
            driver.verify_connectivity.return_value = None
            
            # Mock session
            session = MagicMock()
            session.run.return_value = []
            driver.session.return_value.__enter__.return_value = session
            driver.session.return_value.__exit__.return_value = None
            
            mock.return_value = driver
            yield driver

    def test_query_initialization(self, mock_driver):
        """Test query initialization"""
        from bob.graph.query import GraphQuery
        
        query = GraphQuery()
        query.connect()
        
        assert query._driver is not None
        mock_driver.verify_connectivity.assert_called_once()

    def test_get_dependencies(self, mock_driver):
        """Test get dependencies"""
        from bob.graph.query import GraphQuery
        
        query = GraphQuery()
        query.connect()
        
        repo_id = uuid4()
        deps = query.get_dependencies(
            repo_id=repo_id,
            file_path="src/main.py",
            direction="both",
            max_hops=5,
        )
        
        assert "upstream" in deps
        assert "downstream" in deps
        assert isinstance(deps["upstream"], list)
        assert isinstance(deps["downstream"], list)

    def test_compute_blast_radius(self, mock_driver):
        """Test blast radius computation"""
        from bob.graph.query import GraphQuery
        
        query = GraphQuery()
        query.connect()
        
        # Mock result
        mock_result = [
            {"file_path": "src/affected1.py", "service_name": "service1"},
            {"file_path": "src/affected2.py", "service_name": "service2"},
        ]
        
        session = mock_driver.session.return_value.__enter__.return_value
        session.run.return_value = mock_result
        
        repo_id = uuid4()
        result = query.compute_blast_radius(
            repo_id=repo_id,
            changed_files=["src/main.py"],
            max_hops=5,
        )
        
        assert isinstance(result, BlastRadiusResult)
        assert result.changed_files == ["src/main.py"]
        assert result.max_hops == 5

    def test_get_service_topology(self, mock_driver):
        """Test service topology query"""
        from bob.graph.query import GraphQuery
        
        query = GraphQuery()
        query.connect()
        
        # Mock services and edges
        mock_services = [
            {
                "name": "service1",
                "service_type": "npm",
                "root_path": "services/service1",
                "file_count": 10,
                "dependencies": [],
            }
        ]
        
        mock_edges = [
            {
                "source_service": "service1",
                "target_service": "service2",
                "import_count": 5,
            }
        ]
        
        session = mock_driver.session.return_value.__enter__.return_value
        session.run.side_effect = [mock_services, mock_edges]
        
        repo_id = uuid4()
        topology = query.get_service_topology(repo_id)
        
        assert isinstance(topology, ServiceTopology)
        assert topology.total_services == len(mock_services)
        assert topology.total_edges == len(mock_edges)

    def test_trace_call_chain(self, mock_driver):
        """Test call chain tracing"""
        from bob.graph.query import GraphQuery
        
        query = GraphQuery()
        query.connect()
        
        # Mock call chain
        mock_chain = [
            {
                "chain": ["src/main.py::main", "src/utils.py::helper", "src/db.py::query"],
                "length": 2,
            }
        ]
        
        session = mock_driver.session.return_value.__enter__.return_value
        session.run.return_value = mock_chain
        
        repo_id = uuid4()
        chains = query.trace_call_chain(
            repo_id=repo_id,
            start_function="src/main.py::main",
            end_function="src/db.py::query",
            max_hops=10,
        )
        
        assert isinstance(chains, list)

    def test_get_file_metrics(self, mock_driver):
        """Test file metrics query"""
        from bob.graph.query import GraphQuery
        
        query = GraphQuery()
        query.connect()
        
        # Mock metrics
        mock_metrics = {
            "total_lines": 100,
            "code_lines": 80,
            "comment_lines": 15,
            "language": "python",
            "symbols_count": 5,
            "imports_count": 3,
            "importers_count": 2,
        }
        
        session = mock_driver.session.return_value.__enter__.return_value
        session.run.return_value = MagicMock(single=lambda: mock_metrics)
        
        repo_id = uuid4()
        metrics = query.get_file_metrics(repo_id, "src/main.py")
        
        assert metrics["total_lines"] == 100
        assert metrics["language"] == "python"
        assert "fan_in" in metrics
        assert "fan_out" in metrics


# Made with Bob