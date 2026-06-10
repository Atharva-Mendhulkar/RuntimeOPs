"""
IBM Bob - gRPC Server
Implements gRPC server and BobService servicer
"""

import json
import logging
from typing import Any
from uuid import UUID

import grpc
from fastapi import HTTPException

from bob.api import bob_pb2, bob_pb2_grpc
from bob.api.models import (
    BatchRequest,
    BlastRadiusRequest,
    SearchRequest,
    StackTraceRequest,
    SubQuery,
)
from bob.api.rest import (
    analyze_commit_diff,
    batch_query,
    compute_blast_radius,
    get_dependency_graph,
    get_file,
    health_check,
    resolve_stack_trace,
    search_code,
)
from bob.config import get_settings
from bob.exceptions import (
    AuthenticationError,
    InvalidTokenError,
    RateLimitExceededError,
)
from bob.query.gateway import get_gateway

logger = logging.getLogger(__name__)
settings = get_settings()


class BobServiceServicer(bob_pb2_grpc.BobServiceServicer):
    """gRPC servicer for IBM Bob repository intelligence service"""

    async def _authenticate(self, context: grpc.aio.ServicerContext) -> dict[str, Any]:
        """Authenticate request using JWT token from gRPC metadata"""
        metadata = {}
        invocation_metadata = context.invocation_metadata()
        if invocation_metadata:
            for key, val in invocation_metadata:
                metadata[key.lower()] = val
        authorization = metadata.get("authorization")

        gateway = get_gateway()
        try:
            claims = gateway.verify_token(authorization)
            agent_id = claims.get("org_id", "unknown")
            gateway.check_rate_limit(agent_id)
            return claims
        except AuthenticationError as e:
            logger.warning(f"gRPC Authentication failed: {e.message}")
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, e.message)
        except InvalidTokenError as e:
            logger.warning(f"gRPC Invalid token: {e.message}")
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, e.message)
        except RateLimitExceededError as e:
            logger.warning(f"gRPC Rate limit exceeded: {e.message}")
            await context.abort(grpc.StatusCode.RESOURCE_EXHAUSTED, e.message)

    async def Search(
        self, request: bob_pb2.SearchRequest, context: grpc.aio.ServicerContext
    ) -> bob_pb2.SearchResponse:
        """Semantic code search"""
        claims = await self._authenticate(context)
        try:
            # Map gRPC request to Pydantic SearchRequest
            pydantic_req = SearchRequest(
                repo_id=UUID(request.repo_id),
                query=request.query,
                k=request.k or 10,
                filter=dict(request.filter) if request.filter else None,
            )

            # Invoke existing search logic
            res = await search_code(pydantic_req, claims)

            # Map response
            results = [
                bob_pb2.SearchResult(
                    file_path=r.file_path,
                    symbol_name=r.symbol_name,
                    symbol_type=r.symbol_type,
                    start_line=r.start_line,
                    end_line=r.end_line,
                    content=r.content,
                    confidence=r.confidence,
                    language=r.language,
                )
                for r in res.results
            ]

            return bob_pb2.SearchResponse(
                results=results,
                total=res.total,
                query_time_ms=res.query_time_ms,
                repo_id=res.repo_id,
            )
        except HTTPException as e:
            await context.abort(self._map_status_code(e.status_code), e.detail)
        except (ValueError, TypeError) as e:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(e))
        except Exception as e:
            logger.error(f"gRPC Search failed: {e}", exc_info=True)
            await context.abort(grpc.StatusCode.INTERNAL, str(e))

    async def ResolveStackTrace(
        self, request: bob_pb2.StackTraceRequest, context: grpc.aio.ServicerContext
    ) -> bob_pb2.StackTraceResponse:
        """Resolve stack trace"""
        claims = await self._authenticate(context)
        try:
            # Map request
            pydantic_req = StackTraceRequest(
                repo_id=UUID(request.repo_id),
                trace=request.trace,
            )

            # Invoke REST method logic
            res = await resolve_stack_trace(pydantic_req, claims)

            # Map response
            frames = [
                bob_pb2.StackFrame(
                    file_path=f.file_path,
                    line_number=f.line_number,
                    function=f.function,
                    commit_sha=f.commit_sha,
                    author=f.author,
                    raw_frame=f.raw_frame,
                )
                for f in res.frames
            ]

            return bob_pb2.StackTraceResponse(
                frames=frames,
                total_frames=res.total_frames,
                resolved_frames=res.resolved_frames,
                repo_id=res.repo_id,
            )
        except HTTPException as e:
            await context.abort(self._map_status_code(e.status_code), e.detail)
        except (ValueError, TypeError) as e:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(e))
        except Exception as e:
            logger.error(f"gRPC ResolveStackTrace failed: {e}", exc_info=True)
            await context.abort(grpc.StatusCode.INTERNAL, str(e))

    async def GetDependencyGraph(
        self, request: bob_pb2.DependencyGraphRequest, context: grpc.aio.ServicerContext
    ) -> bob_pb2.DependencyGraphResponse:
        """Retrieve file dependency graph"""
        claims = await self._authenticate(context)
        try:
            # Invoke REST logic directly
            res = await get_dependency_graph(
                repo_id=UUID(request.repo_id),
                file_path=request.file_path,
                hops=request.hops or 3,
                direction=request.direction or "both",
                claims=claims,
            )

            # Map response
            edges = [
                bob_pb2.DependencyEdge(
                    source=e.source,
                    target=e.target,
                    relationship=e.relationship,
                )
                for e in res.edges
            ]

            return bob_pb2.DependencyGraphResponse(
                root_file=res.root_file,
                edges=edges,
                node_count=res.node_count,
                edge_count=res.edge_count,
                max_hops=res.max_hops,
                repo_id=res.repo_id,
            )
        except HTTPException as e:
            await context.abort(self._map_status_code(e.status_code), e.detail)
        except (ValueError, TypeError) as e:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(e))
        except Exception as e:
            logger.error(f"gRPC GetDependencyGraph failed: {e}", exc_info=True)
            await context.abort(grpc.StatusCode.INTERNAL, str(e))

    async def ComputeBlastRadius(
        self, request: bob_pb2.BlastRadiusRequest, context: grpc.aio.ServicerContext
    ) -> bob_pb2.BlastRadiusResponse:
        """Compute blast radius"""
        claims = await self._authenticate(context)
        try:
            # Map request
            pydantic_req = BlastRadiusRequest(
                repo_id=UUID(request.repo_id),
                files=list(request.files),
            )

            # Invoke REST method
            res = await compute_blast_radius(pydantic_req, claims)

            # Map response
            impacted_files = [
                bob_pb2.ImpactedFile(
                    file_path=f.file_path,
                    distance=f.distance,
                    acs_score=f.acs_score,
                    downstream_services=f.downstream_services,
                    test_files=f.test_files,
                )
                for f in res.impacted_files
            ]

            return bob_pb2.BlastRadiusResponse(
                changed_files=res.changed_files,
                impacted_files=impacted_files,
                total_impacted=res.total_impacted,
                affected_services=res.affected_services,
                repo_id=res.repo_id,
            )
        except HTTPException as e:
            await context.abort(self._map_status_code(e.status_code), e.detail)
        except (ValueError, TypeError) as e:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(e))
        except Exception as e:
            logger.error(f"gRPC ComputeBlastRadius failed: {e}", exc_info=True)
            await context.abort(grpc.StatusCode.INTERNAL, str(e))

    async def GetFile(
        self, request: bob_pb2.FileRequest, context: grpc.aio.ServicerContext
    ) -> bob_pb2.FileResponse:
        """Retrieve file content and metadata"""
        claims = await self._authenticate(context)
        try:
            # Invoke REST endpoint method
            res = await get_file(
                repo_id=UUID(request.repo_id),
                file_path=request.file_path,
                claims=claims,
            )

            # Map response
            symbols = [
                bob_pb2.FileSymbol(
                    name=s.name,
                    type=s.type,
                    start_line=s.start_line,
                    end_line=s.end_line,
                )
                for s in res.symbols
            ]

            return bob_pb2.FileResponse(
                file_path=res.file_path,
                content=res.content,
                language=res.language,
                total_lines=res.total_lines,
                symbols=symbols,
                imports=res.imports,
                last_modified=res.last_modified,
                repo_id=res.repo_id,
            )
        except HTTPException as e:
            await context.abort(self._map_status_code(e.status_code), e.detail)
        except (ValueError, TypeError) as e:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(e))
        except Exception as e:
            logger.error(f"gRPC GetFile failed: {e}", exc_info=True)
            await context.abort(grpc.StatusCode.INTERNAL, str(e))

    async def GetCommitDiff(
        self, request: bob_pb2.CommitDiffRequest, context: grpc.aio.ServicerContext
    ) -> bob_pb2.CommitDiffResponse:
        """Analyze commit diff"""
        claims = await self._authenticate(context)
        try:
            # Invoke REST method
            res = await analyze_commit_diff(
                repo_id=UUID(request.repo_id),
                commit_sha=request.commit_sha,
                claims=claims,
            )

            # Map response
            changed_files = [
                bob_pb2.ChangedFile(
                    file_path=f.file_path,
                    change_type=f.change_type,
                    additions=f.additions,
                    deletions=f.deletions,
                    impacted_files=f.impacted_files,
                    test_files=f.test_files,
                )
                for f in res.changed_files
            ]

            return bob_pb2.CommitDiffResponse(
                commit_sha=res.commit_sha,
                author=res.author,
                message=res.message,
                timestamp=res.timestamp,
                changed_files=changed_files,
                total_additions=res.total_additions,
                total_deletions=res.total_deletions,
                repo_id=res.repo_id,
            )
        except HTTPException as e:
            await context.abort(self._map_status_code(e.status_code), e.detail)
        except (ValueError, TypeError) as e:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(e))
        except Exception as e:
            logger.error(f"gRPC GetCommitDiff failed: {e}", exc_info=True)
            await context.abort(grpc.StatusCode.INTERNAL, str(e))

    async def GetHealth(
        self, request: bob_pb2.HealthRequest, context: grpc.aio.ServicerContext
    ) -> bob_pb2.HealthResponse:
        """Expose health status metrics"""
        try:
            # Health check does not require authentication
            res = await health_check()

            # Map response
            return bob_pb2.HealthResponse(
                status=res.status,
                version=res.version,
                services=res.services,
                metrics={k: str(v) for k, v in res.metrics.items()},
                repos_indexed=res.repos_indexed,
                query_p95_ms=res.query_p95_ms,
                index_queue_depth=res.index_queue_depth,
                last_error=res.last_error,
            )
        except HTTPException as e:
            await context.abort(self._map_status_code(e.status_code), e.detail)
        except Exception as e:
            logger.error(f"gRPC GetHealth failed: {e}", exc_info=True)
            await context.abort(grpc.StatusCode.INTERNAL, str(e))

    async def Batch(
        self, request: bob_pb2.BatchRequest, context: grpc.aio.ServicerContext
    ) -> bob_pb2.BatchResponse:
        """Process batch of subqueries"""
        claims = await self._authenticate(context)
        try:
            # Map request to Pydantic BatchRequest
            queries = []
            for q in request.queries:
                params = json.loads(q.params_json)
                queries.append(
                    SubQuery(
                        query_id=q.query_id,
                        query_type=q.query_type,
                        params=params,
                    )
                )

            pydantic_req = BatchRequest(queries=queries)

            # Invoke REST method
            res = await batch_query(pydantic_req, claims)

            # Map response
            results = [
                bob_pb2.SubQueryResult(
                    query_id=r.query_id,
                    success=r.success,
                    result_json=json.dumps(r.result) if r.result else None,
                    error=r.error,
                    execution_time_ms=r.execution_time_ms,
                )
                for r in res.results
            ]

            return bob_pb2.BatchResponse(
                results=results,
                total_queries=res.total_queries,
                successful_queries=res.successful_queries,
                failed_queries=res.failed_queries,
                total_time_ms=res.total_time_ms,
            )
        except HTTPException as e:
            await context.abort(self._map_status_code(e.status_code), e.detail)
        except (ValueError, TypeError) as e:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(e))
        except Exception as e:
            logger.error(f"gRPC Batch failed: {e}", exc_info=True)
            await context.abort(grpc.StatusCode.INTERNAL, str(e))

    def _map_status_code(self, http_code: int) -> grpc.StatusCode:
        """Map HTTP status codes to gRPC status codes"""
        mapping = {
            400: grpc.StatusCode.INVALID_ARGUMENT,
            401: grpc.StatusCode.UNAUTHENTICATED,
            403: grpc.StatusCode.PERMISSION_DENIED,
            404: grpc.StatusCode.NOT_FOUND,
            408: grpc.StatusCode.DEADLINE_EXCEEDED,
            429: grpc.StatusCode.RESOURCE_EXHAUSTED,
            500: grpc.StatusCode.INTERNAL,
            503: grpc.StatusCode.UNAVAILABLE,
            504: grpc.StatusCode.DEADLINE_EXCEEDED,
        }
        return mapping.get(http_code, grpc.StatusCode.INTERNAL)


class GRPCServer:
    """Wrapper to handle the gRPC server lifecycle"""

    def __init__(self, host: str = "0.0.0.0", port: int = 50052) -> None:
        self.host = host
        self.port = port
        self.server: grpc.aio.Server | None = None

    async def start(self) -> None:
        """Start the async gRPC server"""
        self.server = grpc.aio.server()
        bob_pb2_grpc.add_BobServiceServicer_to_server(BobServiceServicer(), self.server)
        listen_addr = f"{self.host}:{self.port}"
        self.server.add_insecure_port(listen_addr)
        logger.info(f"Starting gRPC server on {listen_addr}")
        await self.server.start()

    async def stop(self, grace: float = 5.0) -> None:
        """Gracefully stop the gRPC server"""
        if self.server:
            logger.info("Stopping gRPC server...")
            await self.server.stop(grace)
            logger.info("gRPC server stopped")
