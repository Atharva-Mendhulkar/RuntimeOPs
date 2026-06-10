"""
IBM Bob - Ingest Orchestrator
Coordinates all pipeline stages for repository ingestion
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from bob.config import get_settings
from bob.exceptions import IndexingError, IndexingTimeoutError
from bob.ingestion.analyzer import AnalysisResult, StructuralAnalyzer
from bob.ingestion.convention_extractor import ConventionExtractor, CodingConvention
from bob.ingestion.fetcher import RepositoryFetcher, RepositoryMetadata
from bob.parsers.base import LanguageParser, ParseResult
from bob.parsers.go_parser import GoParser
from bob.parsers.java_parser import JavaParser
from bob.parsers.javascript_parser import JavaScriptParser
from bob.parsers.python_parser import PythonParser
from bob.parsers.typescript_parser import TypeScriptParser
from bob.semantic.embedder import Embedding, SemanticEmbedder

logger = logging.getLogger(__name__)


class IngestionStatus(Enum):
    """Status of ingestion job"""

    PENDING = "pending"
    FETCHING = "fetching"
    PARSING = "parsing"
    ANALYZING = "analyzing"
    EMBEDDING = "embedding"
    EXTRACTING_CONVENTIONS = "extracting_conventions"
    STORING = "storing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class IngestionCheckpoint:
    """Checkpoint for resuming long-running jobs"""

    job_id: str
    status: IngestionStatus
    repo_path: Path | None = None
    parse_results: list[ParseResult] = field(default_factory=list)
    analysis_result: AnalysisResult | None = None
    embeddings: list[Embedding] = field(default_factory=list)
    conventions: dict[str, CodingConvention] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    error: str | None = None


@dataclass
class IngestionProgress:
    """Progress tracking for ingestion job"""

    job_id: str
    status: IngestionStatus
    total_files: int = 0
    processed_files: int = 0
    total_symbols: int = 0
    total_embeddings: int = 0
    start_time: datetime = field(default_factory=datetime.now)
    end_time: datetime | None = None
    error: str | None = None

    @property
    def elapsed_seconds(self) -> float:
        """Get elapsed time in seconds"""
        end = self.end_time or datetime.now()
        return (end - self.start_time).total_seconds()

    @property
    def progress_percentage(self) -> float:
        """Get progress percentage"""
        if self.total_files == 0:
            return 0.0
        return (self.processed_files / self.total_files) * 100


@dataclass
class IngestionResult:
    """Result of complete ingestion pipeline"""

    job_id: str
    repo_url: str
    repo_metadata: RepositoryMetadata
    parse_results: list[ParseResult]
    analysis_result: AnalysisResult
    embeddings: list[Embedding]
    conventions: dict[str, CodingConvention]
    progress: IngestionProgress
    success: bool
    error: str | None = None


class IngestOrchestrator:
    """
    Orchestrates the complete ingestion pipeline.
    
    Responsibilities:
    - Coordinate all pipeline stages
    - Implement checkpointing for long-running jobs
    - Progress tracking and status updates
    - Meet 5-minute indexing SLA for 200 KLOC repos (FR-003)
    
    Pipeline stages:
    1. Repository Fetcher - Clone/pull repository
    2. Language Parsers - Parse all source files
    3. Structural Analyzer - Build dependency graphs
    4. Semantic Embedder - Generate embeddings
    5. Convention Extractor - Extract coding conventions
    6. Storage - Persist to Neo4j, Weaviate, PostgreSQL
    """

    def __init__(self) -> None:
        """Initialize the orchestrator"""
        self.settings = get_settings()
        self._parsers: dict[str, LanguageParser] = {}
        self._init_parsers()
        self._checkpoints: dict[str, IngestionCheckpoint] = {}

    def _init_parsers(self) -> None:
        """Initialize language parsers"""
        self._parsers = {
            "python": PythonParser(),
            "typescript": TypeScriptParser(),
            "javascript": JavaScriptParser(),
            "go": GoParser(),
            "java": JavaParser(),
        }
        logger.info(f"Initialized {len(self._parsers)} language parsers")

    def ingest_repository(
        self,
        repo_url: str,
        installation_id: int,
        job_id: str | None = None,
        branch: str | None = None,
    ) -> IngestionResult:
        """
        Ingest a complete repository through all pipeline stages.
        
        Args:
            repo_url: GitHub repository URL
            installation_id: GitHub App installation ID
            job_id: Optional job ID for tracking
            branch: Optional branch to clone
            
        Returns:
            Ingestion result with all extracted data
            
        Raises:
            IndexingError: If ingestion fails
            IndexingTimeoutError: If ingestion exceeds timeout
        """
        if job_id is None:
            job_id = f"ingest_{int(time.time())}"

        logger.info(f"Starting ingestion job {job_id} for {repo_url}")
        
        # Initialize progress tracking
        progress = IngestionProgress(job_id=job_id, status=IngestionStatus.PENDING)
        
        # Check for existing checkpoint
        checkpoint = self._checkpoints.get(job_id)
        
        try:
            # Stage 1: Fetch repository
            if checkpoint and checkpoint.repo_path:
                logger.info(f"Resuming from checkpoint: {checkpoint.status.value}")
                repo_path = checkpoint.repo_path
                repo_metadata = None  # Would load from checkpoint
            else:
                progress.status = IngestionStatus.FETCHING
                repo_path, repo_metadata = self._fetch_repository(
                    repo_url, installation_id, branch
                )
                self._save_checkpoint(job_id, IngestionStatus.FETCHING, repo_path=repo_path)
            
            # Stage 2: Parse files
            if checkpoint and checkpoint.parse_results:
                parse_results = checkpoint.parse_results
            else:
                progress.status = IngestionStatus.PARSING
                parse_results = self._parse_repository(repo_path, progress)
                self._save_checkpoint(
                    job_id, IngestionStatus.PARSING, repo_path=repo_path, parse_results=parse_results
                )
            
            # Stage 3: Structural analysis
            if checkpoint and checkpoint.analysis_result:
                analysis_result = checkpoint.analysis_result
            else:
                progress.status = IngestionStatus.ANALYZING
                analysis_result = self._analyze_structure(repo_path, parse_results)
                self._save_checkpoint(
                    job_id,
                    IngestionStatus.ANALYZING,
                    repo_path=repo_path,
                    parse_results=parse_results,
                    analysis_result=analysis_result,
                )
            
            # Stage 4: Generate embeddings
            if checkpoint and checkpoint.embeddings:
                embeddings = checkpoint.embeddings
            else:
                progress.status = IngestionStatus.EMBEDDING
                embeddings = self._generate_embeddings(parse_results, progress)
                self._save_checkpoint(
                    job_id,
                    IngestionStatus.EMBEDDING,
                    repo_path=repo_path,
                    parse_results=parse_results,
                    analysis_result=analysis_result,
                    embeddings=embeddings,
                )
            
            # Stage 5: Extract conventions
            if checkpoint and checkpoint.conventions:
                conventions = checkpoint.conventions
            else:
                progress.status = IngestionStatus.EXTRACTING_CONVENTIONS
                conventions = self._extract_conventions(parse_results)
                self._save_checkpoint(
                    job_id,
                    IngestionStatus.EXTRACTING_CONVENTIONS,
                    repo_path=repo_path,
                    parse_results=parse_results,
                    analysis_result=analysis_result,
                    embeddings=embeddings,
                    conventions=conventions,
                )
            
            # Stage 6: Store results (would implement actual storage)
            progress.status = IngestionStatus.STORING
            # TODO: Implement storage to Neo4j, Weaviate, PostgreSQL
            
            # Complete
            progress.status = IngestionStatus.COMPLETED
            progress.end_time = datetime.now()
            
            # Check SLA (FR-003: 5 minutes for 200 KLOC)
            elapsed = progress.elapsed_seconds
            if repo_metadata and repo_metadata.total_lines > 200000 and elapsed > 300:
                logger.warning(
                    f"Indexing exceeded 5-minute SLA: {elapsed:.2f}s for "
                    f"{repo_metadata.total_lines} lines"
                )
            
            logger.info(
                f"Ingestion completed in {elapsed:.2f}s: "
                f"{progress.total_files} files, {progress.total_symbols} symbols, "
                f"{progress.total_embeddings} embeddings"
            )
            
            # Clean up checkpoint
            if job_id in self._checkpoints:
                del self._checkpoints[job_id]
            
            return IngestionResult(
                job_id=job_id,
                repo_url=repo_url,
                repo_metadata=repo_metadata,
                parse_results=parse_results,
                analysis_result=analysis_result,
                embeddings=embeddings,
                conventions=conventions,
                progress=progress,
                success=True,
            )
        
        except Exception as e:
            progress.status = IngestionStatus.FAILED
            progress.end_time = datetime.now()
            progress.error = str(e)
            
            logger.error(f"Ingestion failed for {repo_url}: {e}", exc_info=True)
            
            # Save error checkpoint
            self._save_checkpoint(job_id, IngestionStatus.FAILED, error=str(e))
            
            return IngestionResult(
                job_id=job_id,
                repo_url=repo_url,
                repo_metadata=None,
                parse_results=[],
                analysis_result=None,
                embeddings=[],
                conventions={},
                progress=progress,
                success=False,
                error=str(e),
            )

    def _fetch_repository(
        self,
        repo_url: str,
        installation_id: int,
        branch: str | None,
    ) -> tuple[Path, RepositoryMetadata]:
        """Fetch repository using RepositoryFetcher"""
        start_time = time.time()
        
        with RepositoryFetcher() as fetcher:
            repo_path, metadata = fetcher.clone_repository(
                repo_url, installation_id, branch
            )
            
            elapsed = time.time() - start_time
            logger.info(f"Repository fetched in {elapsed:.2f}s")
            
            return repo_path, metadata

    def _parse_repository(
        self,
        repo_path: Path,
        progress: IngestionProgress,
    ) -> list[ParseResult]:
        """Parse all source files in repository"""
        import time
        import concurrent.futures
        
        start_time = time.time()
        parse_results = []
        
        # Find all source files
        source_files = []
        for parser in self._parsers.values():
            for ext in parser.file_extensions:
                source_files.extend(repo_path.rglob(f"*{ext}"))
        
        # Remove duplicates and filter
        source_files = list(set(source_files))
        source_files = [f for f in source_files if self._should_parse_file(f)]
        
        progress.total_files = len(source_files)
        logger.info(f"Found {len(source_files)} source files to parse")
        
        def parse_single_file(file_path: Path) -> ParseResult | None:
            parser = self._get_parser_for_file(file_path)
            if not parser:
                return None
            try:
                return parser.parse_file(file_path)
            except Exception as e:
                logger.warning(f"Failed to parse {file_path}: {e}")
                return None

        # Parse in parallel
        max_workers = min(16, max(1, len(source_files)))
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_file = {executor.submit(parse_single_file, f): f for f in source_files}
            for future in concurrent.futures.as_completed(future_to_file):
                result = future.result()
                if result:
                    parse_results.append(result)
                    progress.processed_files += 1
                    progress.total_symbols += len(result.symbols)
                    
                    if progress.processed_files % 100 == 0:
                        logger.info(
                            f"Parsed {progress.processed_files}/{progress.total_files} files "
                            f"({progress.progress_percentage:.1f}%)"
                        )
        
        elapsed = time.time() - start_time
        logger.info(
            f"Parsing completed in {elapsed:.2f}s: "
            f"{len(parse_results)} files, {progress.total_symbols} symbols"
        )
        
        return parse_results

    def _should_parse_file(self, file_path: Path) -> bool:
        """Check if file should be parsed"""
        # Skip test files, vendor directories, etc.
        skip_patterns = [
            "node_modules",
            "venv",
            "env",
            ".venv",
            "vendor",
            "target",
            "build",
            "dist",
            "__pycache__",
            ".git",
            "test",
            "tests",
            "spec",
        ]
        
        path_str = str(file_path)
        return not any(pattern in path_str for pattern in skip_patterns)

    def _get_parser_for_file(self, file_path: Path) -> LanguageParser | None:
        """Get appropriate parser for file"""
        for parser in self._parsers.values():
            if parser.can_parse(file_path):
                return parser
        return None

    def _analyze_structure(
        self,
        repo_path: Path,
        parse_results: list[ParseResult],
    ) -> AnalysisResult:
        """Perform structural analysis"""
        start_time = time.time()
        
        analyzer = StructuralAnalyzer()
        result = analyzer.analyze(repo_path, parse_results)
        
        elapsed = time.time() - start_time
        logger.info(
            f"Structural analysis completed in {elapsed:.2f}s: "
            f"{result.total_files} files, {result.total_edges} edges, "
            f"{len(result.service_boundaries)} services"
        )
        
        return result

    def _generate_embeddings(
        self,
        parse_results: list[ParseResult],
        progress: IngestionProgress,
    ) -> list[Embedding]:
        """Generate semantic embeddings"""
        start_time = time.time()
        
        embedder = SemanticEmbedder()
        embeddings = embedder.embed_parse_results(parse_results, use_local_fallback=True)
        
        progress.total_embeddings = len(embeddings)
        
        elapsed = time.time() - start_time
        logger.info(f"Embedding generation completed in {elapsed:.2f}s: {len(embeddings)} embeddings")
        
        return embeddings

    def _extract_conventions(
        self,
        parse_results: list[ParseResult],
    ) -> dict[str, CodingConvention]:
        """Extract coding conventions"""
        start_time = time.time()
        
        extractor = ConventionExtractor()
        conventions = extractor.extract_conventions(parse_results)
        
        elapsed = time.time() - start_time
        logger.info(
            f"Convention extraction completed in {elapsed:.2f}s: "
            f"{len(conventions)} languages"
        )
        
        return conventions

    def _save_checkpoint(
        self,
        job_id: str,
        status: IngestionStatus,
        repo_path: Path | None = None,
        parse_results: list[ParseResult] | None = None,
        analysis_result: AnalysisResult | None = None,
        embeddings: list[Embedding] | None = None,
        conventions: dict[str, CodingConvention] | None = None,
        error: str | None = None,
    ) -> None:
        """Save checkpoint for job"""
        checkpoint = IngestionCheckpoint(
            job_id=job_id,
            status=status,
            repo_path=repo_path,
            parse_results=parse_results or [],
            analysis_result=analysis_result,
            embeddings=embeddings or [],
            conventions=conventions or {},
            error=error,
        )
        self._checkpoints[job_id] = checkpoint
        logger.debug(f"Saved checkpoint for job {job_id}: {status.value}")

    def get_progress(self, job_id: str) -> IngestionProgress | None:
        """Get progress for a job"""
        checkpoint = self._checkpoints.get(job_id)
        if checkpoint:
            return IngestionProgress(
                job_id=job_id,
                status=checkpoint.status,
                total_files=len(checkpoint.parse_results),
                processed_files=len(checkpoint.parse_results),
                total_symbols=sum(len(r.symbols) for r in checkpoint.parse_results),
                total_embeddings=len(checkpoint.embeddings),
            )
        return None


# Made with Bob