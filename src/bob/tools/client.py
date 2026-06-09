"""
IBM Bob - Client SDK
Python SDK for agent developers with sync and async support
"""

import asyncio
import logging
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from bob.config import get_settings
from bob.exceptions import (
    AuthenticationError,
    QueryError,
    QueryTimeoutError,
    ResourceNotFoundError,
)
from bob.tools.models import (
    BlastRadiusResult,
    CodeSearchResult,
    CommitDiff,
    DependencyGraph,
    FileContent,
    RiskContext,
    StackFrame,
)

logger = logging.getLogger(__name__)


class BobClient:
    """
    Bob client for RuntimeOps agents.
    
    Provides both synchronous and asynchronous methods for all 10 Bob tools.
    Includes automatic retry logic, connection pooling, and comprehensive error handling.
    
    Example:
        >>> client = BobClient(
        ...     base_url="http://localhost:8000",
        ...     api_key="your-api-key"
        ... )
        >>> results = client.semantic_search(
        ...     query="authentication middleware",
        ...     repo_id="550e8400-e29b-41d4-a716-446655440000"
        ... )
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
    ):
        """
        Initialize Bob client.
        
        Args:
            base_url: Bob API base URL (defaults to settings.bob_api_url)
            api_key: API key for authentication (defaults to settings.bob_api_key)
            timeout: Request timeout in seconds (default: 30.0)
            max_retries: Maximum number of retries (default: 3)
        """
        settings = get_settings()
        
        self.base_url = (base_url or settings.bob_api_url).rstrip("/")
        self.api_key = api_key or settings.bob_api_key
        self.timeout = timeout
        self.max_retries = max_retries
        
        # Connection pooling
        self._sync_client: httpx.Client | None = None
        self._async_client: httpx.AsyncClient | None = None
        
        logger.info(f"BobClient initialized: base_url={self.base_url}")

    def __enter__(self):
        """Context manager entry"""
        self._sync_client = httpx.Client(
            timeout=self.timeout,
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        if self._sync_client:
            self._sync_client.close()
            self._sync_client = None

    async def __aenter__(self):
        """Async context manager entry"""
        self._async_client = httpx.AsyncClient(
            timeout=self.timeout,
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self._async_client:
            await self._async_client.aclose()
            self._async_client = None

    def _get_headers(self) -> dict[str, str]:
        """Get request headers with authentication"""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _handle_response(self, response: httpx.Response) -> dict[str, Any]:
        """Handle HTTP response and raise appropriate exceptions"""
        if response.status_code == 401:
            raise AuthenticationError("Invalid API key")
        elif response.status_code == 404:
            raise ResourceNotFoundError("Resource not found")
        elif response.status_code >= 500:
            raise QueryError(f"Server error: {response.status_code}")
        
        response.raise_for_status()
        return response.json()

    # ========================================================================
    # Tool 1: Semantic Search
    # ========================================================================

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, QueryError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
    )
    def semantic_search(
        self,
        query: str,
        repo_id: str,
        k: int = 10,
    ) -> list[CodeSearchResult]:
        """
        Synchronous semantic code search.
        
        Args:
            query: Natural language search query
            repo_id: Repository UUID
            k: Number of results to return (default: 10)
        
        Returns:
            List of CodeSearchResult objects
        """
        client = self._sync_client or httpx.Client(timeout=self.timeout)
        
        try:
            response = client.post(
                f"{self.base_url}/api/v1/bob/search",
                json={"repo_id": repo_id, "query": query, "k": k},
                headers=self._get_headers(),
            )
            data = self._handle_response(response)
            
            return [
                CodeSearchResult(
                    file_path=r["file_path"],
                    symbol_name=r["symbol_name"],
                    symbol_type=r["symbol_type"],
                    start_line=r["start_line"],
                    end_line=r["end_line"],
                    content=r["content"],
                    confidence=r["confidence"],
                    language=r["language"],
                    metadata={},
                )
                for r in data["results"]
            ]
        except httpx.TimeoutException as e:
            raise QueryTimeoutError(f"Search timed out: {e}")
        finally:
            if not self._sync_client:
                client.close()

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, QueryError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
    )
    async def semantic_search_async(
        self,
        query: str,
        repo_id: str,
        k: int = 10,
    ) -> list[CodeSearchResult]:
        """
        Asynchronous semantic code search.
        
        Args:
            query: Natural language search query
            repo_id: Repository UUID
            k: Number of results to return (default: 10)
        
        Returns:
            List of CodeSearchResult objects
        """
        client = self._async_client or httpx.AsyncClient(timeout=self.timeout)
        
        try:
            response = await client.post(
                f"{self.base_url}/api/v1/bob/search",
                json={"repo_id": repo_id, "query": query, "k": k},
                headers=self._get_headers(),
            )
            data = self._handle_response(response)
            
            return [
                CodeSearchResult(
                    file_path=r["file_path"],
                    symbol_name=r["symbol_name"],
                    symbol_type=r["symbol_type"],
                    start_line=r["start_line"],
                    end_line=r["end_line"],
                    content=r["content"],
                    confidence=r["confidence"],
                    language=r["language"],
                    metadata={},
                )
                for r in data["results"]
            ]
        except httpx.TimeoutException as e:
            raise QueryTimeoutError(f"Search timed out: {e}")
        finally:
            if not self._async_client:
                await client.aclose()

    # ========================================================================
    # Tool 2: Resolve Stack Trace
    # ========================================================================

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, QueryError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
    )
    def resolve_stack_trace(
        self,
        trace_text: str,
        repo_id: str,
    ) -> list[StackFrame]:
        """Synchronous stack trace resolution"""
        client = self._sync_client or httpx.Client(timeout=self.timeout)
        
        try:
            response = client.post(
                f"{self.base_url}/api/v1/bob/resolve-stack-trace",
                json={"repo_id": repo_id, "trace": trace_text},
                headers=self._get_headers(),
            )
            data = self._handle_response(response)
            
            return [
                StackFrame(
                    file_path=f.get("file_path"),
                    line_number=f.get("line_number"),
                    function=f.get("function"),
                    commit_sha=f.get("commit_sha"),
                    author=f.get("author"),
                    raw_frame=f["raw_frame"],
                )
                for f in data["frames"]
            ]
        finally:
            if not self._sync_client:
                client.close()

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, QueryError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
    )
    async def resolve_stack_trace_async(
        self,
        trace_text: str,
        repo_id: str,
    ) -> list[StackFrame]:
        """Asynchronous stack trace resolution"""
        client = self._async_client or httpx.AsyncClient(timeout=self.timeout)
        
        try:
            response = await client.post(
                f"{self.base_url}/api/v1/bob/resolve-stack-trace",
                json={"repo_id": repo_id, "trace": trace_text},
                headers=self._get_headers(),
            )
            data = self._handle_response(response)
            
            return [
                StackFrame(
                    file_path=f.get("file_path"),
                    line_number=f.get("line_number"),
                    function=f.get("function"),
                    commit_sha=f.get("commit_sha"),
                    author=f.get("author"),
                    raw_frame=f["raw_frame"],
                )
                for f in data["frames"]
            ]
        finally:
            if not self._async_client:
                await client.aclose()

    # ========================================================================
    # Tool 3: Get Dependency Graph
    # ========================================================================

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, QueryError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
    )
    def get_dependency_graph(
        self,
        file_path: str,
        repo_id: str,
        hops: int = 3,
        direction: str = "both",
    ) -> DependencyGraph:
        """Synchronous dependency graph retrieval"""
        client = self._sync_client or httpx.Client(timeout=self.timeout)
        
        try:
            response = client.get(
                f"{self.base_url}/api/v1/bob/dependency-graph",
                params={
                    "repo_id": repo_id,
                    "file_path": file_path,
                    "hops": hops,
                    "direction": direction,
                },
                headers=self._get_headers(),
            )
            data = self._handle_response(response)
            
            from bob.tools.models import DependencyEdge
            
            edges = [
                DependencyEdge(
                    source=e["source"],
                    target=e["target"],
                    relationship=e["relationship"],
                    metadata={},
                )
                for e in data["edges"]
            ]
            
            nodes = {file_path}
            for edge in edges:
                nodes.add(edge.source)
                nodes.add(edge.target)
            
            return DependencyGraph(
                root_file=file_path,
                edges=edges,
                nodes=list(nodes),
                node_count=len(nodes),
                edge_count=len(edges),
                max_hops=hops,
            )
        finally:
            if not self._sync_client:
                client.close()

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, QueryError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
    )
    async def get_dependency_graph_async(
        self,
        file_path: str,
        repo_id: str,
        hops: int = 3,
        direction: str = "both",
    ) -> DependencyGraph:
        """Asynchronous dependency graph retrieval"""
        client = self._async_client or httpx.AsyncClient(timeout=self.timeout)
        
        try:
            response = await client.get(
                f"{self.base_url}/api/v1/bob/dependency-graph",
                params={
                    "repo_id": repo_id,
                    "file_path": file_path,
                    "hops": hops,
                    "direction": direction,
                },
                headers=self._get_headers(),
            )
            data = self._handle_response(response)
            
            from bob.tools.models import DependencyEdge
            
            edges = [
                DependencyEdge(
                    source=e["source"],
                    target=e["target"],
                    relationship=e["relationship"],
                    metadata={},
                )
                for e in data["edges"]
            ]
            
            nodes = {file_path}
            for edge in edges:
                nodes.add(edge.source)
                nodes.add(edge.target)
            
            return DependencyGraph(
                root_file=file_path,
                edges=edges,
                nodes=list(nodes),
                node_count=len(nodes),
                edge_count=len(edges),
                max_hops=hops,
            )
        finally:
            if not self._async_client:
                await client.aclose()

    # ========================================================================
    # Tool 4: Get Blast Radius
    # ========================================================================

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, QueryError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
    )
    def get_blast_radius(
        self,
        files: list[str],
        repo_id: str,
    ) -> BlastRadiusResult:
        """Synchronous blast radius computation"""
        client = self._sync_client or httpx.Client(timeout=self.timeout)
        
        try:
            response = client.post(
                f"{self.base_url}/api/v1/bob/blast-radius",
                json={"repo_id": repo_id, "files": files},
                headers=self._get_headers(),
            )
            data = self._handle_response(response)
            
            from bob.tools.models import ImpactedFile
            
            impacted_files = [
                ImpactedFile(
                    file_path=f["file_path"],
                    distance=f["distance"],
                    acs_score=f.get("acs_score"),
                    downstream_services=f.get("downstream_services", []),
                    test_files=f.get("test_files", []),
                )
                for f in data["impacted_files"]
            ]
            
            return BlastRadiusResult(
                changed_files=data["changed_files"],
                impacted_files=impacted_files,
                total_impacted=data["total_impacted"],
                affected_services=data["affected_services"],
            )
        finally:
            if not self._sync_client:
                client.close()

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, QueryError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
    )
    async def get_blast_radius_async(
        self,
        files: list[str],
        repo_id: str,
    ) -> BlastRadiusResult:
        """Asynchronous blast radius computation"""
        client = self._async_client or httpx.AsyncClient(timeout=self.timeout)
        
        try:
            response = await client.post(
                f"{self.base_url}/api/v1/bob/blast-radius",
                json={"repo_id": repo_id, "files": files},
                headers=self._get_headers(),
            )
            data = self._handle_response(response)
            
            from bob.tools.models import ImpactedFile
            
            impacted_files = [
                ImpactedFile(
                    file_path=f["file_path"],
                    distance=f["distance"],
                    acs_score=f.get("acs_score"),
                    downstream_services=f.get("downstream_services", []),
                    test_files=f.get("test_files", []),
                )
                for f in data["impacted_files"]
            ]
            
            return BlastRadiusResult(
                changed_files=data["changed_files"],
                impacted_files=impacted_files,
                total_impacted=data["total_impacted"],
                affected_services=data["affected_services"],
            )
        finally:
            if not self._async_client:
                await client.aclose()

    # ========================================================================
    # Tool 5: Get File Content
    # ========================================================================

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, QueryError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
    )
    def get_file_content(
        self,
        file_path: str,
        repo_id: str,
    ) -> FileContent:
        """Synchronous file content retrieval"""
        client = self._sync_client or httpx.Client(timeout=self.timeout)
        
        try:
            response = client.get(
                f"{self.base_url}/api/v1/bob/file",
                params={"repo_id": repo_id, "file_path": file_path},
                headers=self._get_headers(),
            )
            data = self._handle_response(response)
            
            from bob.tools.models import FileSymbol
            
            symbols = [
                FileSymbol(
                    name=s["name"],
                    type=s["type"],
                    start_line=s["start_line"],
                    end_line=s["end_line"],
                    docstring=None,
                )
                for s in data.get("symbols", [])
            ]
            
            return FileContent(
                file_path=data["file_path"],
                content=data["content"],
                language=data["language"],
                total_lines=data["total_lines"],
                symbols=symbols,
                imports=data.get("imports", []),
                last_modified=None,
            )
        finally:
            if not self._sync_client:
                client.close()

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, QueryError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
    )
    async def get_file_content_async(
        self,
        file_path: str,
        repo_id: str,
    ) -> FileContent:
        """Asynchronous file content retrieval"""
        client = self._async_client or httpx.AsyncClient(timeout=self.timeout)
        
        try:
            response = await client.get(
                f"{self.base_url}/api/v1/bob/file",
                params={"repo_id": repo_id, "file_path": file_path},
                headers=self._get_headers(),
            )
            data = self._handle_response(response)
            
            from bob.tools.models import FileSymbol
            
            symbols = [
                FileSymbol(
                    name=s["name"],
                    type=s["type"],
                    start_line=s["start_line"],
                    end_line=s["end_line"],
                    docstring=None,
                )
                for s in data.get("symbols", [])
            ]
            
            return FileContent(
                file_path=data["file_path"],
                content=data["content"],
                language=data["language"],
                total_lines=data["total_lines"],
                symbols=symbols,
                imports=data.get("imports", []),
                last_modified=None,
            )
        finally:
            if not self._async_client:
                await client.aclose()

    # ========================================================================
    # Tool 6: Get Commit Diff
    # ========================================================================

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, QueryError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
    )
    def get_commit_diff(
        self,
        commit_sha: str,
        repo_id: str,
    ) -> CommitDiff:
        """Synchronous commit diff retrieval"""
        client = self._sync_client or httpx.Client(timeout=self.timeout)
        
        try:
            response = client.get(
                f"{self.base_url}/api/v1/bob/commit-diff",
                params={"repo_id": repo_id, "commit_sha": commit_sha},
                headers=self._get_headers(),
            )
            data = self._handle_response(response)
            
            from bob.tools.models import ChangedFile
            
            changed_files = [
                ChangedFile(
                    file_path=f["file_path"],
                    change_type=f["change_type"],
                    additions=f["additions"],
                    deletions=f["deletions"],
                    impacted_files=f.get("impacted_files", []),
                    test_files=f.get("test_files", []),
                )
                for f in data.get("changed_files", [])
            ]
            
            return CommitDiff(
                commit_sha=data["commit_sha"],
                author=data.get("author"),
                message=data.get("message"),
                timestamp=None,
                changed_files=changed_files,
                total_additions=data.get("total_additions", 0),
                total_deletions=data.get("total_deletions", 0),
            )
        finally:
            if not self._sync_client:
                client.close()

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, QueryError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
    )
    async def get_commit_diff_async(
        self,
        commit_sha: str,
        repo_id: str,
    ) -> CommitDiff:
        """Asynchronous commit diff retrieval"""
        client = self._async_client or httpx.AsyncClient(timeout=self.timeout)
        
        try:
            response = await client.get(
                f"{self.base_url}/api/v1/bob/commit-diff",
                params={"repo_id": repo_id, "commit_sha": commit_sha},
                headers=self._get_headers(),
            )
            data = self._handle_response(response)
            
            from bob.tools.models import ChangedFile
            
            changed_files = [
                ChangedFile(
                    file_path=f["file_path"],
                    change_type=f["change_type"],
                    additions=f["additions"],
                    deletions=f["deletions"],
                    impacted_files=f.get("impacted_files", []),
                    test_files=f.get("test_files", []),
                )
                for f in data.get("changed_files", [])
            ]
            
            return CommitDiff(
                commit_sha=data["commit_sha"],
                author=data.get("author"),
                message=data.get("message"),
                timestamp=None,
                changed_files=changed_files,
                total_additions=data.get("total_additions", 0),
                total_deletions=data.get("total_deletions", 0),
            )
        finally:
            if not self._async_client:
                await client.aclose()

    # ========================================================================
    # Additional helper methods for tools 7-10
    # ========================================================================

    def get_test_map(self, source_files: list[str], repo_id: str) -> list[str]:
        """Get test files for source files (uses bob_tools.get_test_map)"""
        from bob.tools.bob_tools import get_test_map
        return get_test_map(source_files, repo_id)

    async def get_test_map_async(self, source_files: list[str], repo_id: str) -> list[str]:
        """Async get test files for source files"""
        from bob.tools.bob_tools import get_test_map
        return await asyncio.to_thread(get_test_map, source_files, repo_id)

    def get_conventions(self, service_path: str, repo_id: str) -> dict[str, Any]:
        """Get coding conventions for service (uses bob_tools.get_conventions)"""
        from bob.tools.bob_tools import get_conventions
        return get_conventions(service_path, repo_id)

    async def get_conventions_async(self, service_path: str, repo_id: str) -> dict[str, Any]:
        """Async get coding conventions for service"""
        from bob.tools.bob_tools import get_conventions
        return await asyncio.to_thread(get_conventions, service_path, repo_id)

    def get_risk_context(self, files: list[str], repo_id: str) -> list[RiskContext]:
        """Get risk context for files (uses bob_tools.get_risk_context)"""
        from bob.tools.bob_tools import get_risk_context
        return get_risk_context(files, repo_id)

    async def get_risk_context_async(self, files: list[str], repo_id: str) -> list[RiskContext]:
        """Async get risk context for files"""
        from bob.tools.bob_tools import get_risk_context
        return await asyncio.to_thread(get_risk_context, files, repo_id)

    def trigger_reindex(self, repo_id: str, scope: str = "incremental") -> str:
        """Trigger repository reindex (uses bob_tools.trigger_reindex)"""
        from bob.tools.bob_tools import trigger_reindex
        return trigger_reindex(repo_id, scope)

    async def trigger_reindex_async(self, repo_id: str, scope: str = "incremental") -> str:
        """Async trigger repository reindex"""
        from bob.tools.bob_tools import trigger_reindex
        return await asyncio.to_thread(trigger_reindex, repo_id, scope)


# Made with Bob