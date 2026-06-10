from collections.abc import Iterable as _Iterable
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar
from typing import Optional as _Optional
from typing import Union as _Union

from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from google.protobuf.internal import containers as _containers

DESCRIPTOR: _descriptor.FileDescriptor

class SearchRequest(_message.Message):
    __slots__ = ("repo_id", "query", "k", "filter")

    class FilterEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...

    REPO_ID_FIELD_NUMBER: _ClassVar[int]
    QUERY_FIELD_NUMBER: _ClassVar[int]
    K_FIELD_NUMBER: _ClassVar[int]
    FILTER_FIELD_NUMBER: _ClassVar[int]
    repo_id: str
    query: str
    k: int
    filter: _containers.ScalarMap[str, str]
    def __init__(
        self,
        repo_id: _Optional[str] = ...,
        query: _Optional[str] = ...,
        k: _Optional[int] = ...,
        filter: _Optional[_Mapping[str, str]] = ...,
    ) -> None: ...

class SearchResult(_message.Message):
    __slots__ = (
        "file_path",
        "symbol_name",
        "symbol_type",
        "start_line",
        "end_line",
        "content",
        "confidence",
        "language",
    )
    FILE_PATH_FIELD_NUMBER: _ClassVar[int]
    SYMBOL_NAME_FIELD_NUMBER: _ClassVar[int]
    SYMBOL_TYPE_FIELD_NUMBER: _ClassVar[int]
    START_LINE_FIELD_NUMBER: _ClassVar[int]
    END_LINE_FIELD_NUMBER: _ClassVar[int]
    CONTENT_FIELD_NUMBER: _ClassVar[int]
    CONFIDENCE_FIELD_NUMBER: _ClassVar[int]
    LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    file_path: str
    symbol_name: str
    symbol_type: str
    start_line: int
    end_line: int
    content: str
    confidence: float
    language: str
    def __init__(
        self,
        file_path: _Optional[str] = ...,
        symbol_name: _Optional[str] = ...,
        symbol_type: _Optional[str] = ...,
        start_line: _Optional[int] = ...,
        end_line: _Optional[int] = ...,
        content: _Optional[str] = ...,
        confidence: _Optional[float] = ...,
        language: _Optional[str] = ...,
    ) -> None: ...

class SearchResponse(_message.Message):
    __slots__ = ("results", "total", "query_time_ms", "repo_id")
    RESULTS_FIELD_NUMBER: _ClassVar[int]
    TOTAL_FIELD_NUMBER: _ClassVar[int]
    QUERY_TIME_MS_FIELD_NUMBER: _ClassVar[int]
    REPO_ID_FIELD_NUMBER: _ClassVar[int]
    results: _containers.RepeatedCompositeFieldContainer[SearchResult]
    total: int
    query_time_ms: float
    repo_id: str
    def __init__(
        self,
        results: _Optional[_Iterable[_Union[SearchResult, _Mapping]]] = ...,
        total: _Optional[int] = ...,
        query_time_ms: _Optional[float] = ...,
        repo_id: _Optional[str] = ...,
    ) -> None: ...

class StackTraceRequest(_message.Message):
    __slots__ = ("repo_id", "trace")
    REPO_ID_FIELD_NUMBER: _ClassVar[int]
    TRACE_FIELD_NUMBER: _ClassVar[int]
    repo_id: str
    trace: str
    def __init__(self, repo_id: _Optional[str] = ..., trace: _Optional[str] = ...) -> None: ...

class StackFrame(_message.Message):
    __slots__ = ("file_path", "line_number", "function", "commit_sha", "author", "raw_frame")
    FILE_PATH_FIELD_NUMBER: _ClassVar[int]
    LINE_NUMBER_FIELD_NUMBER: _ClassVar[int]
    FUNCTION_FIELD_NUMBER: _ClassVar[int]
    COMMIT_SHA_FIELD_NUMBER: _ClassVar[int]
    AUTHOR_FIELD_NUMBER: _ClassVar[int]
    RAW_FRAME_FIELD_NUMBER: _ClassVar[int]
    file_path: str
    line_number: int
    function: str
    commit_sha: str
    author: str
    raw_frame: str
    def __init__(
        self,
        file_path: _Optional[str] = ...,
        line_number: _Optional[int] = ...,
        function: _Optional[str] = ...,
        commit_sha: _Optional[str] = ...,
        author: _Optional[str] = ...,
        raw_frame: _Optional[str] = ...,
    ) -> None: ...

class StackTraceResponse(_message.Message):
    __slots__ = ("frames", "total_frames", "resolved_frames", "repo_id")
    FRAMES_FIELD_NUMBER: _ClassVar[int]
    TOTAL_FRAMES_FIELD_NUMBER: _ClassVar[int]
    RESOLVED_FRAMES_FIELD_NUMBER: _ClassVar[int]
    REPO_ID_FIELD_NUMBER: _ClassVar[int]
    frames: _containers.RepeatedCompositeFieldContainer[StackFrame]
    total_frames: int
    resolved_frames: int
    repo_id: str
    def __init__(
        self,
        frames: _Optional[_Iterable[_Union[StackFrame, _Mapping]]] = ...,
        total_frames: _Optional[int] = ...,
        resolved_frames: _Optional[int] = ...,
        repo_id: _Optional[str] = ...,
    ) -> None: ...

class DependencyGraphRequest(_message.Message):
    __slots__ = ("repo_id", "file_path", "hops", "direction")
    REPO_ID_FIELD_NUMBER: _ClassVar[int]
    FILE_PATH_FIELD_NUMBER: _ClassVar[int]
    HOPS_FIELD_NUMBER: _ClassVar[int]
    DIRECTION_FIELD_NUMBER: _ClassVar[int]
    repo_id: str
    file_path: str
    hops: int
    direction: str
    def __init__(
        self,
        repo_id: _Optional[str] = ...,
        file_path: _Optional[str] = ...,
        hops: _Optional[int] = ...,
        direction: _Optional[str] = ...,
    ) -> None: ...

class DependencyEdge(_message.Message):
    __slots__ = ("source", "target", "relationship")
    SOURCE_FIELD_NUMBER: _ClassVar[int]
    TARGET_FIELD_NUMBER: _ClassVar[int]
    RELATIONSHIP_FIELD_NUMBER: _ClassVar[int]
    source: str
    target: str
    relationship: str
    def __init__(
        self,
        source: _Optional[str] = ...,
        target: _Optional[str] = ...,
        relationship: _Optional[str] = ...,
    ) -> None: ...

class DependencyGraphResponse(_message.Message):
    __slots__ = ("root_file", "edges", "node_count", "edge_count", "max_hops", "repo_id")
    ROOT_FILE_FIELD_NUMBER: _ClassVar[int]
    EDGES_FIELD_NUMBER: _ClassVar[int]
    NODE_COUNT_FIELD_NUMBER: _ClassVar[int]
    EDGE_COUNT_FIELD_NUMBER: _ClassVar[int]
    MAX_HOPS_FIELD_NUMBER: _ClassVar[int]
    REPO_ID_FIELD_NUMBER: _ClassVar[int]
    root_file: str
    edges: _containers.RepeatedCompositeFieldContainer[DependencyEdge]
    node_count: int
    edge_count: int
    max_hops: int
    repo_id: str
    def __init__(
        self,
        root_file: _Optional[str] = ...,
        edges: _Optional[_Iterable[_Union[DependencyEdge, _Mapping]]] = ...,
        node_count: _Optional[int] = ...,
        edge_count: _Optional[int] = ...,
        max_hops: _Optional[int] = ...,
        repo_id: _Optional[str] = ...,
    ) -> None: ...

class BlastRadiusRequest(_message.Message):
    __slots__ = ("repo_id", "files")
    REPO_ID_FIELD_NUMBER: _ClassVar[int]
    FILES_FIELD_NUMBER: _ClassVar[int]
    repo_id: str
    files: _containers.RepeatedScalarFieldContainer[str]
    def __init__(
        self, repo_id: _Optional[str] = ..., files: _Optional[_Iterable[str]] = ...
    ) -> None: ...

class ImpactedFile(_message.Message):
    __slots__ = ("file_path", "distance", "acs_score", "downstream_services", "test_files")
    FILE_PATH_FIELD_NUMBER: _ClassVar[int]
    DISTANCE_FIELD_NUMBER: _ClassVar[int]
    ACS_SCORE_FIELD_NUMBER: _ClassVar[int]
    DOWNSTREAM_SERVICES_FIELD_NUMBER: _ClassVar[int]
    TEST_FILES_FIELD_NUMBER: _ClassVar[int]
    file_path: str
    distance: int
    acs_score: float
    downstream_services: _containers.RepeatedScalarFieldContainer[str]
    test_files: _containers.RepeatedScalarFieldContainer[str]
    def __init__(
        self,
        file_path: _Optional[str] = ...,
        distance: _Optional[int] = ...,
        acs_score: _Optional[float] = ...,
        downstream_services: _Optional[_Iterable[str]] = ...,
        test_files: _Optional[_Iterable[str]] = ...,
    ) -> None: ...

class BlastRadiusResponse(_message.Message):
    __slots__ = (
        "changed_files",
        "impacted_files",
        "total_impacted",
        "affected_services",
        "repo_id",
    )
    CHANGED_FILES_FIELD_NUMBER: _ClassVar[int]
    IMPACTED_FILES_FIELD_NUMBER: _ClassVar[int]
    TOTAL_IMPACTED_FIELD_NUMBER: _ClassVar[int]
    AFFECTED_SERVICES_FIELD_NUMBER: _ClassVar[int]
    REPO_ID_FIELD_NUMBER: _ClassVar[int]
    changed_files: _containers.RepeatedScalarFieldContainer[str]
    impacted_files: _containers.RepeatedCompositeFieldContainer[ImpactedFile]
    total_impacted: int
    affected_services: _containers.RepeatedScalarFieldContainer[str]
    repo_id: str
    def __init__(
        self,
        changed_files: _Optional[_Iterable[str]] = ...,
        impacted_files: _Optional[_Iterable[_Union[ImpactedFile, _Mapping]]] = ...,
        total_impacted: _Optional[int] = ...,
        affected_services: _Optional[_Iterable[str]] = ...,
        repo_id: _Optional[str] = ...,
    ) -> None: ...

class FileRequest(_message.Message):
    __slots__ = ("repo_id", "file_path")
    REPO_ID_FIELD_NUMBER: _ClassVar[int]
    FILE_PATH_FIELD_NUMBER: _ClassVar[int]
    repo_id: str
    file_path: str
    def __init__(self, repo_id: _Optional[str] = ..., file_path: _Optional[str] = ...) -> None: ...

class FileSymbol(_message.Message):
    __slots__ = ("name", "type", "start_line", "end_line")
    NAME_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    START_LINE_FIELD_NUMBER: _ClassVar[int]
    END_LINE_FIELD_NUMBER: _ClassVar[int]
    name: str
    type: str
    start_line: int
    end_line: int
    def __init__(
        self,
        name: _Optional[str] = ...,
        type: _Optional[str] = ...,
        start_line: _Optional[int] = ...,
        end_line: _Optional[int] = ...,
    ) -> None: ...

class FileResponse(_message.Message):
    __slots__ = (
        "file_path",
        "content",
        "language",
        "total_lines",
        "symbols",
        "imports",
        "last_modified",
        "repo_id",
    )
    FILE_PATH_FIELD_NUMBER: _ClassVar[int]
    CONTENT_FIELD_NUMBER: _ClassVar[int]
    LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    TOTAL_LINES_FIELD_NUMBER: _ClassVar[int]
    SYMBOLS_FIELD_NUMBER: _ClassVar[int]
    IMPORTS_FIELD_NUMBER: _ClassVar[int]
    LAST_MODIFIED_FIELD_NUMBER: _ClassVar[int]
    REPO_ID_FIELD_NUMBER: _ClassVar[int]
    file_path: str
    content: str
    language: str
    total_lines: int
    symbols: _containers.RepeatedCompositeFieldContainer[FileSymbol]
    imports: _containers.RepeatedScalarFieldContainer[str]
    last_modified: str
    repo_id: str
    def __init__(
        self,
        file_path: _Optional[str] = ...,
        content: _Optional[str] = ...,
        language: _Optional[str] = ...,
        total_lines: _Optional[int] = ...,
        symbols: _Optional[_Iterable[_Union[FileSymbol, _Mapping]]] = ...,
        imports: _Optional[_Iterable[str]] = ...,
        last_modified: _Optional[str] = ...,
        repo_id: _Optional[str] = ...,
    ) -> None: ...

class CommitDiffRequest(_message.Message):
    __slots__ = ("repo_id", "commit_sha")
    REPO_ID_FIELD_NUMBER: _ClassVar[int]
    COMMIT_SHA_FIELD_NUMBER: _ClassVar[int]
    repo_id: str
    commit_sha: str
    def __init__(self, repo_id: _Optional[str] = ..., commit_sha: _Optional[str] = ...) -> None: ...

class ChangedFile(_message.Message):
    __slots__ = (
        "file_path",
        "change_type",
        "additions",
        "deletions",
        "impacted_files",
        "test_files",
    )
    FILE_PATH_FIELD_NUMBER: _ClassVar[int]
    CHANGE_TYPE_FIELD_NUMBER: _ClassVar[int]
    ADDITIONS_FIELD_NUMBER: _ClassVar[int]
    DELETIONS_FIELD_NUMBER: _ClassVar[int]
    IMPACTED_FILES_FIELD_NUMBER: _ClassVar[int]
    TEST_FILES_FIELD_NUMBER: _ClassVar[int]
    file_path: str
    change_type: str
    additions: int
    deletions: int
    impacted_files: _containers.RepeatedScalarFieldContainer[str]
    test_files: _containers.RepeatedScalarFieldContainer[str]
    def __init__(
        self,
        file_path: _Optional[str] = ...,
        change_type: _Optional[str] = ...,
        additions: _Optional[int] = ...,
        deletions: _Optional[int] = ...,
        impacted_files: _Optional[_Iterable[str]] = ...,
        test_files: _Optional[_Iterable[str]] = ...,
    ) -> None: ...

class CommitDiffResponse(_message.Message):
    __slots__ = (
        "commit_sha",
        "author",
        "message",
        "timestamp",
        "changed_files",
        "total_additions",
        "total_deletions",
        "repo_id",
    )
    COMMIT_SHA_FIELD_NUMBER: _ClassVar[int]
    AUTHOR_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    CHANGED_FILES_FIELD_NUMBER: _ClassVar[int]
    TOTAL_ADDITIONS_FIELD_NUMBER: _ClassVar[int]
    TOTAL_DELETIONS_FIELD_NUMBER: _ClassVar[int]
    REPO_ID_FIELD_NUMBER: _ClassVar[int]
    commit_sha: str
    author: str
    message: str
    timestamp: str
    changed_files: _containers.RepeatedCompositeFieldContainer[ChangedFile]
    total_additions: int
    total_deletions: int
    repo_id: str
    def __init__(
        self,
        commit_sha: _Optional[str] = ...,
        author: _Optional[str] = ...,
        message: _Optional[str] = ...,
        timestamp: _Optional[str] = ...,
        changed_files: _Optional[_Iterable[_Union[ChangedFile, _Mapping]]] = ...,
        total_additions: _Optional[int] = ...,
        total_deletions: _Optional[int] = ...,
        repo_id: _Optional[str] = ...,
    ) -> None: ...

class HealthRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class HealthResponse(_message.Message):
    __slots__ = (
        "status",
        "version",
        "services",
        "metrics",
        "repos_indexed",
        "query_p95_ms",
        "index_queue_depth",
        "last_error",
    )

    class ServicesEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...

    class MetricsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...

    STATUS_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    SERVICES_FIELD_NUMBER: _ClassVar[int]
    METRICS_FIELD_NUMBER: _ClassVar[int]
    REPOS_INDEXED_FIELD_NUMBER: _ClassVar[int]
    QUERY_P95_MS_FIELD_NUMBER: _ClassVar[int]
    INDEX_QUEUE_DEPTH_FIELD_NUMBER: _ClassVar[int]
    LAST_ERROR_FIELD_NUMBER: _ClassVar[int]
    status: str
    version: str
    services: _containers.ScalarMap[str, str]
    metrics: _containers.ScalarMap[str, str]
    repos_indexed: int
    query_p95_ms: float
    index_queue_depth: int
    last_error: str
    def __init__(
        self,
        status: _Optional[str] = ...,
        version: _Optional[str] = ...,
        services: _Optional[_Mapping[str, str]] = ...,
        metrics: _Optional[_Mapping[str, str]] = ...,
        repos_indexed: _Optional[int] = ...,
        query_p95_ms: _Optional[float] = ...,
        index_queue_depth: _Optional[int] = ...,
        last_error: _Optional[str] = ...,
    ) -> None: ...

class SubQuery(_message.Message):
    __slots__ = ("query_id", "query_type", "params_json")
    QUERY_ID_FIELD_NUMBER: _ClassVar[int]
    QUERY_TYPE_FIELD_NUMBER: _ClassVar[int]
    PARAMS_JSON_FIELD_NUMBER: _ClassVar[int]
    query_id: str
    query_type: str
    params_json: str
    def __init__(
        self,
        query_id: _Optional[str] = ...,
        query_type: _Optional[str] = ...,
        params_json: _Optional[str] = ...,
    ) -> None: ...

class BatchRequest(_message.Message):
    __slots__ = ("queries",)
    QUERIES_FIELD_NUMBER: _ClassVar[int]
    queries: _containers.RepeatedCompositeFieldContainer[SubQuery]
    def __init__(self, queries: _Optional[_Iterable[_Union[SubQuery, _Mapping]]] = ...) -> None: ...

class SubQueryResult(_message.Message):
    __slots__ = ("query_id", "success", "result_json", "error", "execution_time_ms")
    QUERY_ID_FIELD_NUMBER: _ClassVar[int]
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    RESULT_JSON_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    EXECUTION_TIME_MS_FIELD_NUMBER: _ClassVar[int]
    query_id: str
    success: bool
    result_json: str
    error: str
    execution_time_ms: float
    def __init__(
        self,
        query_id: _Optional[str] = ...,
        success: bool = ...,
        result_json: _Optional[str] = ...,
        error: _Optional[str] = ...,
        execution_time_ms: _Optional[float] = ...,
    ) -> None: ...

class BatchResponse(_message.Message):
    __slots__ = (
        "results",
        "total_queries",
        "successful_queries",
        "failed_queries",
        "total_time_ms",
    )
    RESULTS_FIELD_NUMBER: _ClassVar[int]
    TOTAL_QUERIES_FIELD_NUMBER: _ClassVar[int]
    SUCCESSFUL_QUERIES_FIELD_NUMBER: _ClassVar[int]
    FAILED_QUERIES_FIELD_NUMBER: _ClassVar[int]
    TOTAL_TIME_MS_FIELD_NUMBER: _ClassVar[int]
    results: _containers.RepeatedCompositeFieldContainer[SubQueryResult]
    total_queries: int
    successful_queries: int
    failed_queries: int
    total_time_ms: float
    def __init__(
        self,
        results: _Optional[_Iterable[_Union[SubQueryResult, _Mapping]]] = ...,
        total_queries: _Optional[int] = ...,
        successful_queries: _Optional[int] = ...,
        failed_queries: _Optional[int] = ...,
        total_time_ms: _Optional[float] = ...,
    ) -> None: ...
