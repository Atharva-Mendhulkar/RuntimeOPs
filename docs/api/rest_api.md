# REST API Reference

The Repository Intelligence Service exposes a REST API at prefix `/api/v1/bob`. All mutating and retrieval endpoints require standard Bearer JWT authorization.

---

## Endpoints

### 1. Semantic Search
- **Endpoint**: `POST /api/v1/bob/search`
- **Description**: Natural language search over the codebase.
- **Request Body**:
  ```json
  {
    "repo_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "query": "connection pool configuration",
    "k": 10,
    "filter": {
      "language": "python",
      "symbol_type": "class"
    }
  }
  ```
- **Response**:
  ```json
  {
    "results": [
      {
        "file_path": "src/db/redis_client.py",
        "symbol_name": "ConnectionPool",
        "symbol_type": "class",
        "start_line": 10,
        "end_line": 50,
        "content": "class ConnectionPool: ...",
        "confidence": 0.95,
        "language": "python"
      }
    ],
    "total": 1,
    "query_time_ms": 23.4,
    "repo_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6"
  }
  ```

---

### 2. Resolve Stack Trace
- **Endpoint**: `POST /api/v1/bob/resolve-stack-trace`
- **Description**: Resolves stack trace strings back to git commits and file paths.
- **Request Body**:
  ```json
  {
    "repo_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "trace": "File \"src/auth.py\", line 42, in login\n  raise ConnectionError"
  }
  ```
- **Response**:
  ```json
  {
    "frames": [
      {
        "raw_frame": "File \"src/auth.py\", line 42, in login",
        "file_path": "src/auth.py",
        "line_number": 42,
        "function": "login",
        "commit_sha": "abc1234",
        "author": "Alice"
      }
    ],
    "total_frames": 2,
    "resolved_frames": 1,
    "repo_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6"
  }
  ```

---

### 3. Dependency Graph
- **Endpoint**: `GET /api/v1/bob/dependency-graph`
- **Query Parameters**:
  - `repo_id`: Repository UUID
  - `file_path`: Source file relative path
  - `hops`: Graph traversal depth (max 10, default 3)
  - `direction`: Traversal direction (`upstream`, `downstream`, `both`)
- **Response**:
  ```json
  {
    "root_file": "src/main.py",
    "edges": [
      {
        "source": "src/config.py",
        "target": "src/main.py",
        "relationship": "imports"
      }
    ],
    "node_count": 2,
    "edge_count": 1,
    "max_hops": 3,
    "repo_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6"
  }
  ```

---

### 4. Blast Radius
- **Endpoint**: `POST /api/v1/bob/blast-radius`
- **Description**: Estimates downstream impacts and affected services for file changes.
- **Request Body**:
  ```json
  {
    "repo_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "files": ["src/db/connection.py"]
  }
  ```
- **Response**:
  ```json
  {
    "changed_files": ["src/db/connection.py"],
    "impacted_files": [
      {
        "file_path": "src/checkout/service.py",
        "distance": 1,
        "acs_score": 0.92,
        "downstream_services": ["checkout-api"],
        "test_files": ["tests/checkout/test_service.py"]
      }
    ],
    "total_impacted": 1,
    "affected_services": ["checkout-api"],
    "repo_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6"
  }
  ```

---

### 5. File Retrieval
- **Endpoint**: `GET /api/v1/bob/file`
- **Query Parameters**:
  - `repo_id`: Repository UUID
  - `file_path`: File path
- **Response**:
  ```json
  {
    "file_path": "src/main.py",
    "content": "print('hello')",
    "language": "python",
    "total_lines": 1,
    "symbols": [],
    "imports": [],
    "last_modified": null,
    "repo_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6"
  }
  ```

---

### 6. Commit Diff
- **Endpoint**: `GET /api/v1/bob/commit-diff`
- **Query Parameters**:
  - `repo_id`: Repository UUID
  - `commit_sha`: Git commit SHA
- **Response**:
  ```json
  {
    "commit_sha": "abc1234",
    "author": "Alice",
    "message": "fix DB pool leak",
    "timestamp": "2026-05-19T10:00:00Z",
    "changed_files": ["src/db/connection.py"],
    "total_additions": 4,
    "total_deletions": 2,
    "repo_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6"
  }
  ```

---

### 7. Health Check
- **Endpoint**: `GET /api/v1/bob/health`
- **Description**: Diagnoses connection health of databases (Redis, Neo4j, PostgreSQL, Weaviate).
- **Response**:
  ```json
  {
    "status": "healthy",
    "version": "1.0.0",
    "services": {
      "neo4j": "healthy",
      "weaviate": "healthy",
      "postgres": "healthy",
      "redis": "healthy"
    },
    "metrics": {
      "vector_count": 10500,
      "repos_indexed": 4,
      "cache_hit_rate": 0.92
    },
    "repos_indexed": 4,
    "query_p95_ms": 12.5,
    "index_queue_depth": 0,
    "last_error": null
  }
  ```

---

### 8. Batch Query
- **Endpoint**: `POST /api/v1/bob/batch`
- **Description**: Executes multiple query requests in parallel (max 20).
- **Request Body**:
  ```json
  {
    "queries": [
      {
        "query_id": "q1",
        "query_type": "search",
        "params": {
          "repo_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
          "query": "checkout payment"
        }
      }
    ]
  }
  ```
- **Response**:
  ```json
  {
    "results": [
      {
        "query_id": "q1",
        "success": true,
        "result": { ... },
        "error": null,
        "execution_time_ms": 15.2
      }
    ],
    "total_queries": 1,
    "successful_queries": 1,
    "failed_queries": 0,
    "total_time_ms": 16.5
  }
  ```
