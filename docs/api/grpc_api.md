# gRPC API Reference

The Repository Intelligence Service hosts a high-performance gRPC interface concurrently with the REST API on port `50052`.

---

## Service Definition

Defined in [bob.proto](file:///Users/atharvamendhulkar/Desktop/RuntimeOps/src/bob/api/protos/bob.proto):

```protobuf
syntax = "proto3";

package bob.api;

service BobService {
  rpc Search(SearchRequest) returns (SearchResponse);
  rpc ResolveStackTrace(StackTraceRequest) returns (StackTraceResponse);
  rpc GetDependencyGraph(DependencyGraphRequest) returns (DependencyGraphResponse);
  rpc ComputeBlastRadius(BlastRadiusRequest) returns (BlastRadiusResponse);
  rpc GetFile(FileRequest) returns (FileResponse);
  rpc GetCommitDiff(CommitDiffRequest) returns (CommitDiffResponse);
  rpc GetHealth(HealthRequest) returns (HealthResponse);
  rpc Batch(BatchRequest) returns (BatchResponse);
}
```

---

## Methods and Messages

### 1. Search
- **RPC**: `Search`
- **Request**: `SearchRequest`
  - `repo_id` (string): Repository UUID
  - `query` (string): Search query
  - `k` (int32): Limit results
- **Response**: `SearchResponse`
  - `results` (repeated SearchResult): Code snippets matching query
  - `total` (int32): Total results count

---

### 2. ResolveStackTrace
- **RPC**: `ResolveStackTrace`
- **Request**: `StackTraceRequest`
  - `repo_id` (string): Repository UUID
  - `trace` (string): Stack trace string
- **Response**: `StackTraceResponse`
  - `frames` (repeated StackFrame): Parsed stack trace frames
  - `total_frames` (int32): Total line frames
  - `resolved_frames` (int32): Successfully resolved frames

---

### 3. GetDependencyGraph
- **RPC**: `GetDependencyGraph`
- **Request**: `DependencyGraphRequest`
  - `repo_id` (string): Repository UUID
  - `file_path` (string): Source file path
  - `hops` (int32): Maximum search depth
  - `direction` (string): Traversal direction (`upstream`, `downstream`, `both`)
- **Response**: `DependencyGraphResponse`
  - `root_file` (string): Root file path
  - `edges` (repeated DependencyEdge): Dependency edges
  - `node_count` (int32): Total distinct files
  - `edge_count` (int32): Total edges

---

### 4. ComputeBlastRadius
- **RPC**: `ComputeBlastRadius`
- **Request**: `BlastRadiusRequest`
  - `repo_id` (string): Repository UUID
  - `files` (repeated string): Changed files
- **Response**: `BlastRadiusResponse`
  - `changed_files` (repeated string): Input files
  - `impacted_files` (repeated ImpactedFile): Downstream impacted files enriched with ACS scores
  - `affected_services` (repeated string): Downstream services impacted

---

### 5. GetHealth
- **RPC**: `GetHealth`
- **Request**: `HealthRequest` (empty)
- **Response**: `HealthResponse`
  - `status` (string): Service health state
  - `version` (string): Code version
  - `services` (map<string, string>): Backend connection states
