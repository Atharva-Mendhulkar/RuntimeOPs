"""
IBM Bob - Repository Fetcher
Handles repository cloning, incremental updates, and diff extraction
"""

import logging
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import git
from github import Auth, Github, GithubIntegration

from bob.config import get_settings
from bob.exceptions import (
    ConfigurationError,
    RepositoryCloneError,
    RepositoryNotFoundError,
)

logger = logging.getLogger(__name__)


@dataclass
class CommitDiff:
    """Represents a commit diff with metadata"""

    commit_sha: str
    author: str
    timestamp: datetime
    message: str
    files_changed: list[str]
    additions: int
    deletions: int
    diff_content: str


@dataclass
class RepositoryMetadata:
    """Repository metadata extracted during fetch"""

    repo_url: str
    default_branch: str
    last_commit_sha: str
    last_commit_timestamp: datetime
    total_files: int
    total_lines: int
    languages: dict[str, int]  # language -> line count


class RepositoryFetcher:
    """
    Fetches and manages repository clones with GitHub App authentication.

    Responsibilities:
    - Clone repositories to ephemeral workspace
    - Handle incremental pulls on push webhooks
    - Extract commit diffs
    - Meet 10-second registration SLA (FR-001)
    """

    def __init__(self) -> None:
        """Initialize the repository fetcher with GitHub App credentials"""
        self.settings = get_settings()
        self._validate_config()
        self._github_client: Github | None = None
        self._workspace_dir: Path | None = None

    def _validate_config(self) -> None:
        """Validate required configuration is present"""
        if not self.settings.github_app_id:
            raise ConfigurationError(
                "GitHub App ID not configured",
                details={"config_key": "github_app_id"},
            )
        if not self.settings.github_app_private_key_path:
            raise ConfigurationError(
                "GitHub App private key path not configured",
                details={"config_key": "github_app_private_key_path"},
            )

    def _get_github_client(self, installation_id: int) -> Github:
        """
        Get authenticated GitHub client for a specific installation.

        Args:
            installation_id: GitHub App installation ID

        Returns:
            Authenticated GitHub client

        Raises:
            ConfigurationError: If authentication fails
        """
        try:
            # Read private key
            key_path = Path(self.settings.github_app_private_key_path)
            if not key_path.exists():
                raise ConfigurationError(
                    f"GitHub App private key not found at {key_path}",
                    details={"path": str(key_path)},
                )

            with open(key_path, "r") as key_file:
                private_key = key_file.read()

            # Create GitHub Integration
            integration = GithubIntegration(
                self.settings.github_app_id,
                private_key,
            )

            # Get installation access token
            auth = integration.get_access_token(installation_id)

            # Create authenticated client
            return Github(auth=Auth.Token(auth.token))

        except Exception as e:
            raise ConfigurationError(
                f"Failed to authenticate with GitHub: {str(e)}",
                details={"installation_id": installation_id},
            ) from e

    def _create_workspace(self) -> Path:
        """
        Create ephemeral workspace directory for repository clones.

        Returns:
            Path to workspace directory
        """
        workspace = Path(tempfile.mkdtemp(prefix="bob_repo_"))
        logger.info(f"Created workspace at {workspace}")
        return workspace

    def _cleanup_workspace(self) -> None:
        """Clean up ephemeral workspace directory"""
        if self._workspace_dir and self._workspace_dir.exists():
            try:
                shutil.rmtree(self._workspace_dir)
                logger.info(f"Cleaned up workspace at {self._workspace_dir}")
            except Exception as e:
                logger.warning(f"Failed to cleanup workspace: {e}")
            finally:
                self._workspace_dir = None

    def clone_repository(
        self,
        repo_url: str,
        installation_id: int,
        branch: str | None = None,
    ) -> tuple[Path, RepositoryMetadata]:
        """
        Clone a repository to ephemeral workspace.

        Args:
            repo_url: GitHub repository URL (e.g., https://github.com/owner/repo)
            installation_id: GitHub App installation ID
            branch: Branch to clone (defaults to repository default branch)

        Returns:
            Tuple of (workspace_path, repository_metadata)

        Raises:
            RepositoryNotFoundError: If repository doesn't exist or is inaccessible
            RepositoryCloneError: If clone operation fails
        """
        start_time = datetime.now()
        logger.info(f"Cloning repository {repo_url}")

        try:
            # Get authenticated client
            github_client = self._get_github_client(installation_id)

            # Parse repo owner and name from URL
            parts = repo_url.rstrip("/").split("/")
            repo_owner, repo_name = parts[-2], parts[-1].replace(".git", "")

            # Get repository object
            try:
                gh_repo = github_client.get_repo(f"{repo_owner}/{repo_name}")
            except Exception as e:
                raise RepositoryNotFoundError(
                    f"Repository {repo_owner}/{repo_name} not found or not accessible",
                    details={"repo_url": repo_url, "error": str(e)},
                ) from e

            # Determine branch
            if not branch:
                branch = gh_repo.default_branch

            # Create workspace
            self._workspace_dir = self._create_workspace()
            repo_path = self._workspace_dir / repo_name

            # Clone repository with authentication
            auth_url = repo_url.replace(
                "https://",
                f"https://x-access-token:{github_client.get_user().login}@",
            )

            try:
                repo = git.Repo.clone_from(
                    auth_url,
                    repo_path,
                    branch=branch,
                    depth=1,  # Shallow clone for speed
                )
            except git.GitCommandError as e:
                raise RepositoryCloneError(
                    f"Failed to clone repository: {str(e)}",
                    details={"repo_url": repo_url, "branch": branch},
                ) from e

            # Extract metadata
            metadata = self._extract_metadata(repo, gh_repo, repo_path)

            elapsed = (datetime.now() - start_time).total_seconds()
            logger.info(
                f"Successfully cloned {repo_url} in {elapsed:.2f}s "
                f"({metadata.total_files} files, {metadata.total_lines} lines)"
            )

            # Check SLA (FR-001: 10 seconds)
            if elapsed > 10:
                logger.warning(f"Clone exceeded 10s SLA: {elapsed:.2f}s for {repo_url}")

            return repo_path, metadata

        except (RepositoryNotFoundError, RepositoryCloneError):
            self._cleanup_workspace()
            raise
        except Exception as e:
            self._cleanup_workspace()
            raise RepositoryCloneError(
                f"Unexpected error during clone: {str(e)}",
                details={"repo_url": repo_url},
            ) from e

    def pull_updates(
        self,
        repo_path: Path,
        installation_id: int,
    ) -> tuple[list[CommitDiff], RepositoryMetadata]:
        """
        Pull latest updates for an existing repository clone.

        Args:
            repo_path: Path to existing repository clone
            installation_id: GitHub App installation ID

        Returns:
            Tuple of (list of commit diffs since last pull, updated metadata)

        Raises:
            RepositoryCloneError: If pull operation fails
        """
        start_time = datetime.now()
        logger.info(f"Pulling updates for {repo_path}")

        try:
            repo = git.Repo(repo_path)

            # Get current HEAD before pull
            old_commit = repo.head.commit.hexsha

            # Pull latest changes
            origin = repo.remotes.origin
            origin.pull()

            # Get new HEAD after pull
            new_commit = repo.head.commit.hexsha

            # Extract diffs if there are new commits
            diffs = []
            if old_commit != new_commit:
                diffs = self._extract_commit_diffs(repo, old_commit, new_commit)

            # Extract updated metadata
            # Get GitHub repo object for language stats
            github_client = self._get_github_client(installation_id)
            repo_url = origin.url
            parts = repo_url.rstrip("/").split("/")
            repo_owner = parts[-2]
            repo_name = parts[-1].replace(".git", "")
            gh_repo = github_client.get_repo(f"{repo_owner}/{repo_name}")

            metadata = self._extract_metadata(repo, gh_repo, repo_path)

            elapsed = (datetime.now() - start_time).total_seconds()
            logger.info(
                f"Successfully pulled updates in {elapsed:.2f}s " f"({len(diffs)} new commits)"
            )

            return diffs, metadata

        except Exception as e:
            raise RepositoryCloneError(
                f"Failed to pull updates: {str(e)}",
                details={"repo_path": str(repo_path)},
            ) from e

    def _extract_metadata(
        self,
        repo: git.Repo,
        gh_repo: Any,
        repo_path: Path,
    ) -> RepositoryMetadata:
        """
        Extract repository metadata.

        Args:
            repo: GitPython Repo object
            gh_repo: PyGithub Repository object
            repo_path: Path to repository clone

        Returns:
            Repository metadata
        """
        # Get last commit info
        last_commit = repo.head.commit

        # Count files and lines
        total_files = 0
        total_lines = 0

        for file_path in repo_path.rglob("*"):
            if file_path.is_file() and not self._should_skip_file(file_path):
                total_files += 1
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        total_lines += sum(1 for _ in f)
                except (UnicodeDecodeError, PermissionError):
                    # Skip binary or unreadable files
                    pass

        # Get language statistics from GitHub API
        languages = {}
        try:
            languages = gh_repo.get_languages()
        except Exception as e:
            logger.warning(f"Failed to get language stats: {e}")

        return RepositoryMetadata(
            repo_url=repo.remotes.origin.url,
            default_branch=repo.active_branch.name,
            last_commit_sha=last_commit.hexsha,
            last_commit_timestamp=datetime.fromtimestamp(last_commit.committed_date),
            total_files=total_files,
            total_lines=total_lines,
            languages=languages,
        )

    def _extract_commit_diffs(
        self,
        repo: git.Repo,
        old_commit: str,
        new_commit: str,
    ) -> list[CommitDiff]:
        """
        Extract diffs for commits between old and new commit.

        Args:
            repo: GitPython Repo object
            old_commit: Old commit SHA
            new_commit: New commit SHA

        Returns:
            List of commit diffs
        """
        diffs = []

        # Get commits between old and new
        commits = list(repo.iter_commits(f"{old_commit}..{new_commit}"))

        for commit in commits:
            # Get diff stats
            stats = commit.stats.total

            # Get changed files
            files_changed = []
            if commit.parents:
                parent = commit.parents[0]
                diff_index = parent.diff(commit)
                files_changed = [item.a_path or item.b_path for item in diff_index]

            # Get full diff content
            diff_content = ""
            if commit.parents:
                diff_content = repo.git.diff(commit.parents[0], commit)

            diffs.append(
                CommitDiff(
                    commit_sha=commit.hexsha,
                    author=str(commit.author),
                    timestamp=datetime.fromtimestamp(commit.committed_date),
                    message=commit.message.strip(),
                    files_changed=files_changed,
                    additions=stats["insertions"],
                    deletions=stats["deletions"],
                    diff_content=diff_content,
                )
            )

        return diffs

    def _should_skip_file(self, file_path: Path) -> bool:
        """
        Determine if a file should be skipped during processing.

        Args:
            file_path: Path to file

        Returns:
            True if file should be skipped
        """
        # Skip hidden files and directories
        if any(part.startswith(".") for part in file_path.parts):
            return True

        # Skip common non-source directories
        skip_dirs = {
            "node_modules",
            "venv",
            "env",
            "__pycache__",
            "dist",
            "build",
            "target",
            ".git",
        }
        if any(part in skip_dirs for part in file_path.parts):
            return True

        # Skip binary and non-source extensions
        skip_extensions = {
            ".pyc",
            ".pyo",
            ".so",
            ".dylib",
            ".dll",
            ".exe",
            ".bin",
            ".jpg",
            ".jpeg",
            ".png",
            ".gif",
            ".pdf",
            ".zip",
            ".tar",
            ".gz",
            ".lock",
        }
        if file_path.suffix.lower() in skip_extensions:
            return True

        return False

    def get_file_content(self, repo_path: Path, file_path: str) -> str:
        """
        Get content of a specific file from repository.

        Args:
            repo_path: Path to repository clone
            file_path: Relative path to file within repository

        Returns:
            File content as string

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        full_path = repo_path / file_path

        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        try:
            with open(full_path, "r", encoding="utf-8") as f:
                return f.read()
        except UnicodeDecodeError as e:
            raise ValueError(f"File is not valid UTF-8: {file_path}") from e

    def cleanup(self) -> None:
        """Clean up resources and workspace"""
        self._cleanup_workspace()

    def __enter__(self) -> "RepositoryFetcher":
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - cleanup workspace"""
        self.cleanup()


# Made with Bob
