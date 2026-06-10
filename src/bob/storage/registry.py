"""
IBM Bob - PostgreSQL Index Registry
Tracks repository metadata and indexing status
"""

import logging
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, relationship, sessionmaker

from bob.config import get_settings
from bob.exceptions import ResourceNotFoundError

logger = logging.getLogger(__name__)

Base = declarative_base()


class IndexRegistry(Base):
    """Repository index registry table"""

    __tablename__ = "index_registry"

    repo_id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    github_url = Column(String, nullable=False, unique=True, index=True)
    status = Column(String(20), nullable=False, index=True)
    last_full_index = Column(DateTime(timezone=True), nullable=True)
    last_incremental = Column(DateTime(timezone=True), nullable=True)
    file_count = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    coverage_pct = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    # Relationships
    access_grants = relationship(
        "RepoAccess", back_populates="repository", cascade="all, delete-orphan"
    )
    jobs = relationship("IndexJob", back_populates="repository", cascade="all, delete-orphan")


class RepoAccess(Base):
    """Repository access control table"""

    __tablename__ = "repo_access"

    id = Column(Integer, primary_key=True, autoincrement=True)
    repo_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("index_registry.repo_id", ondelete="CASCADE"),
        nullable=False,
    )
    org_id = Column(String(255), nullable=False, index=True)
    granted_at = Column(DateTime(timezone=True), default=func.now())

    # Relationships
    repository = relationship("IndexRegistry", back_populates="access_grants")


class IndexJob(Base):
    """Index job tracking table"""

    __tablename__ = "index_jobs"

    job_id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    repo_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("index_registry.repo_id", ondelete="CASCADE"),
        nullable=False,
    )
    job_type = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False, index=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
    files_processed = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=func.now())

    # Relationships
    repository = relationship("IndexRegistry", back_populates="jobs")


class IndexRegistryManager:
    """
    Manages PostgreSQL index registry.

    Responsibilities:
    - CRUD operations for repository metadata
    - Track indexing status: idle, indexing, error, stale
    - Store coverage metrics
    - Staleness detection (>10 min since push = stale)
    - Query methods for health dashboard
    """

    def __init__(self) -> None:
        """Initialize the registry manager"""
        self.settings = get_settings()
        self._engine = None
        self._session_factory = None

    def __enter__(self) -> "IndexRegistryManager":
        """Context manager entry"""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit"""
        self.close()

    def connect(self) -> None:
        """Connect to PostgreSQL database"""
        try:
            self._engine = create_engine(
                self.settings.postgres_dsn,
                pool_size=20,
                max_overflow=40,
                pool_pre_ping=True,
                pool_recycle=3600,
                echo=self.settings.is_development,
            )

            # Create tables if they don't exist
            Base.metadata.create_all(self._engine)

            # Create session factory
            self._session_factory = sessionmaker(bind=self._engine)

            logger.info("Connected to PostgreSQL registry")

        except Exception as e:
            logger.error(f"Failed to connect to PostgreSQL: {e}")
            raise

    def close(self) -> None:
        """Close database connection"""
        if self._engine:
            self._engine.dispose()
            logger.info("Closed PostgreSQL connection")

    def _get_session(self) -> Session:
        """Get a database session"""
        if not self._session_factory:
            raise RuntimeError("Database not connected")
        return self._session_factory()

    def create_repository(
        self,
        github_url: str,
        status: str = "idle",
    ) -> UUID:
        """
        Create a new repository entry.

        Args:
            github_url: GitHub repository URL
            status: Initial status

        Returns:
            Repository UUID
        """
        session = self._get_session()

        try:
            repo = IndexRegistry(
                github_url=github_url,
                status=status,
            )
            session.add(repo)
            session.commit()

            repo_id = repo.repo_id
            logger.info(f"Created repository entry: {github_url} ({repo_id})")
            return repo_id

        except Exception as e:
            session.rollback()
            logger.error(f"Failed to create repository: {e}")
            raise
        finally:
            session.close()

    def get_repository(self, repo_id: UUID) -> dict[str, Any]:
        """
        Get repository by ID.

        Args:
            repo_id: Repository UUID

        Returns:
            Repository data as dictionary
        """
        session = self._get_session()

        try:
            repo = session.query(IndexRegistry).filter_by(repo_id=repo_id).first()

            if not repo:
                raise ResourceNotFoundError(
                    f"Repository not found: {repo_id}",
                    details={"repo_id": str(repo_id)},
                )

            return {
                "repo_id": str(repo.repo_id),
                "github_url": repo.github_url,
                "status": repo.status,
                "last_full_index": (
                    repo.last_full_index.isoformat() if repo.last_full_index else None
                ),
                "last_incremental": (
                    repo.last_incremental.isoformat() if repo.last_incremental else None
                ),
                "file_count": repo.file_count,
                "error_count": repo.error_count,
                "coverage_pct": repo.coverage_pct,
                "created_at": repo.created_at.isoformat(),
                "updated_at": repo.updated_at.isoformat(),
            }

        finally:
            session.close()

    def get_repository_by_url(self, github_url: str) -> dict[str, Any] | None:
        """
        Get repository by GitHub URL.

        Args:
            github_url: GitHub repository URL

        Returns:
            Repository data or None if not found
        """
        session = self._get_session()

        try:
            repo = session.query(IndexRegistry).filter_by(github_url=github_url).first()

            if not repo:
                return None

            return {
                "repo_id": str(repo.repo_id),
                "github_url": repo.github_url,
                "status": repo.status,
                "last_full_index": (
                    repo.last_full_index.isoformat() if repo.last_full_index else None
                ),
                "last_incremental": (
                    repo.last_incremental.isoformat() if repo.last_incremental else None
                ),
                "file_count": repo.file_count,
                "error_count": repo.error_count,
                "coverage_pct": repo.coverage_pct,
                "created_at": repo.created_at.isoformat(),
                "updated_at": repo.updated_at.isoformat(),
            }

        finally:
            session.close()

    def update_repository_status(
        self,
        repo_id: UUID,
        status: str,
        error_message: str | None = None,
    ) -> None:
        """
        Update repository status.

        Args:
            repo_id: Repository UUID
            status: New status (idle, indexing, error, stale)
            error_message: Optional error message
        """
        session = self._get_session()

        try:
            repo = session.query(IndexRegistry).filter_by(repo_id=repo_id).first()

            if not repo:
                raise ResourceNotFoundError(f"Repository not found: {repo_id}")

            repo.status = status

            if status == "error" and error_message:
                repo.error_count += 1

            session.commit()
            logger.info(f"Updated repository status: {repo_id} -> {status}")

        except Exception as e:
            session.rollback()
            logger.error(f"Failed to update repository status: {e}")
            raise
        finally:
            session.close()

    def update_repository_metrics(
        self,
        repo_id: UUID,
        file_count: int,
        error_count: int,
        coverage_pct: float,
    ) -> None:
        """
        Update repository metrics.

        Args:
            repo_id: Repository UUID
            file_count: Total file count
            error_count: Error count
            coverage_pct: Coverage percentage
        """
        session = self._get_session()

        try:
            repo = session.query(IndexRegistry).filter_by(repo_id=repo_id).first()

            if not repo:
                raise ResourceNotFoundError(f"Repository not found: {repo_id}")

            repo.file_count = file_count
            repo.error_count = error_count
            repo.coverage_pct = coverage_pct

            session.commit()
            logger.info(f"Updated repository metrics: {repo_id}")

        except Exception as e:
            session.rollback()
            logger.error(f"Failed to update repository metrics: {e}")
            raise
        finally:
            session.close()

    def mark_full_index_complete(self, repo_id: UUID) -> None:
        """
        Mark full index as complete.

        Args:
            repo_id: Repository UUID
        """
        session = self._get_session()

        try:
            repo = session.query(IndexRegistry).filter_by(repo_id=repo_id).first()

            if not repo:
                raise ResourceNotFoundError(f"Repository not found: {repo_id}")

            repo.last_full_index = datetime.utcnow()
            repo.status = "idle"

            session.commit()
            logger.info(f"Marked full index complete: {repo_id}")

        except Exception as e:
            session.rollback()
            logger.error(f"Failed to mark full index complete: {e}")
            raise
        finally:
            session.close()

    def mark_incremental_update_complete(self, repo_id: UUID) -> None:
        """
        Mark incremental update as complete.

        Args:
            repo_id: Repository UUID
        """
        session = self._get_session()

        try:
            repo = session.query(IndexRegistry).filter_by(repo_id=repo_id).first()

            if not repo:
                raise ResourceNotFoundError(f"Repository not found: {repo_id}")

            repo.last_incremental = datetime.utcnow()
            repo.status = "idle"

            session.commit()
            logger.info(f"Marked incremental update complete: {repo_id}")

        except Exception as e:
            session.rollback()
            logger.error(f"Failed to mark incremental update complete: {e}")
            raise
        finally:
            session.close()

    def detect_stale_repositories(self, threshold_minutes: int = 10) -> list[dict[str, Any]]:
        """
        Detect stale repositories (not updated recently).

        Args:
            threshold_minutes: Staleness threshold in minutes

        Returns:
            List of stale repositories
        """
        session = self._get_session()

        try:
            threshold_time = datetime.utcnow() - timedelta(minutes=threshold_minutes)

            stale_repos = (
                session.query(IndexRegistry)
                .filter(
                    IndexRegistry.last_incremental < threshold_time,
                    IndexRegistry.status != "indexing",
                )
                .all()
            )

            results = []
            for repo in stale_repos:
                results.append(
                    {
                        "repo_id": str(repo.repo_id),
                        "github_url": repo.github_url,
                        "last_incremental": (
                            repo.last_incremental.isoformat() if repo.last_incremental else None
                        ),
                        "status": repo.status,
                    }
                )

            logger.info(f"Found {len(results)} stale repositories")
            return results

        finally:
            session.close()

    def list_repositories(
        self,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """
        List repositories with optional filtering.

        Args:
            status: Optional status filter
            limit: Maximum number of results
            offset: Offset for pagination

        Returns:
            List of repositories
        """
        session = self._get_session()

        try:
            query = session.query(IndexRegistry)

            if status:
                query = query.filter_by(status=status)

            repos = query.limit(limit).offset(offset).all()

            results = []
            for repo in repos:
                results.append(
                    {
                        "repo_id": str(repo.repo_id),
                        "github_url": repo.github_url,
                        "status": repo.status,
                        "file_count": repo.file_count,
                        "error_count": repo.error_count,
                        "coverage_pct": repo.coverage_pct,
                        "last_full_index": (
                            repo.last_full_index.isoformat() if repo.last_full_index else None
                        ),
                        "last_incremental": (
                            repo.last_incremental.isoformat() if repo.last_incremental else None
                        ),
                    }
                )

            return results

        finally:
            session.close()

    def delete_repository(self, repo_id: UUID) -> None:
        """
        Delete a repository entry.

        Args:
            repo_id: Repository UUID
        """
        session = self._get_session()

        try:
            repo = session.query(IndexRegistry).filter_by(repo_id=repo_id).first()

            if not repo:
                raise ResourceNotFoundError(f"Repository not found: {repo_id}")

            session.delete(repo)
            session.commit()
            logger.info(f"Deleted repository: {repo_id}")

        except Exception as e:
            session.rollback()
            logger.error(f"Failed to delete repository: {e}")
            raise
        finally:
            session.close()

    def create_index_job(
        self,
        repo_id: UUID,
        job_type: str,
    ) -> UUID:
        """
        Create a new index job.

        Args:
            repo_id: Repository UUID
            job_type: Job type (full, incremental)

        Returns:
            Job UUID
        """
        session = self._get_session()

        try:
            job = IndexJob(
                repo_id=repo_id,
                job_type=job_type,
                status="pending",
            )
            session.add(job)
            session.commit()

            job_id = job.job_id
            logger.info(f"Created index job: {job_id} ({job_type})")
            return job_id

        except Exception as e:
            session.rollback()
            logger.error(f"Failed to create index job: {e}")
            raise
        finally:
            session.close()

    def update_job_status(
        self,
        job_id: UUID,
        status: str,
        error_message: str | None = None,
        files_processed: int | None = None,
    ) -> None:
        """
        Update job status.

        Args:
            job_id: Job UUID
            status: New status (pending, running, completed, failed)
            error_message: Optional error message
            files_processed: Optional files processed count
        """
        session = self._get_session()

        try:
            job = session.query(IndexJob).filter_by(job_id=job_id).first()

            if not job:
                raise ResourceNotFoundError(f"Job not found: {job_id}")

            job.status = status

            if status == "running" and not job.started_at:
                job.started_at = datetime.utcnow()

            if status in ("completed", "failed"):
                job.completed_at = datetime.utcnow()

            if error_message:
                job.error_message = error_message

            if files_processed is not None:
                job.files_processed = files_processed

            session.commit()
            logger.info(f"Updated job status: {job_id} -> {status}")

        except Exception as e:
            session.rollback()
            logger.error(f"Failed to update job status: {e}")
            raise
        finally:
            session.close()

    def get_health_metrics(self) -> dict[str, Any]:
        """
        Get health metrics for dashboard.

        Returns:
            Dictionary with health metrics
        """
        session = self._get_session()

        try:
            total_repos = session.query(func.count(IndexRegistry.repo_id)).scalar()

            status_counts = {}
            for status in ["idle", "indexing", "error", "stale"]:
                count = (
                    session.query(func.count(IndexRegistry.repo_id))
                    .filter_by(status=status)
                    .scalar()
                )
                status_counts[status] = count

            avg_coverage = session.query(func.avg(IndexRegistry.coverage_pct)).scalar() or 0.0

            total_files = session.query(func.sum(IndexRegistry.file_count)).scalar() or 0

            total_errors = session.query(func.sum(IndexRegistry.error_count)).scalar() or 0

            # Recent jobs
            recent_jobs = (
                session.query(IndexJob).order_by(IndexJob.created_at.desc()).limit(10).all()
            )

            jobs_data = []
            for job in recent_jobs:
                jobs_data.append(
                    {
                        "job_id": str(job.job_id),
                        "repo_id": str(job.repo_id),
                        "job_type": job.job_type,
                        "status": job.status,
                        "files_processed": job.files_processed,
                        "created_at": job.created_at.isoformat(),
                    }
                )

            metrics = {
                "total_repositories": total_repos,
                "status_counts": status_counts,
                "average_coverage": round(avg_coverage, 2),
                "total_files_indexed": total_files,
                "total_errors": total_errors,
                "recent_jobs": jobs_data,
            }

            logger.info(f"Health metrics: {metrics}")
            return metrics

        finally:
            session.close()


# Made with Bob
