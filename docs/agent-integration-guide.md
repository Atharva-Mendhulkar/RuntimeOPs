# Bob Agent Integration Guide

## Overview

This guide explains how RuntimeOps agents integrate with Bob's tool suite to perform incident analysis, root cause identification, and automated remediation.

## Table of Contents

1. [Quick Start](#quick-start)
2. [Tool Suite Overview](#tool-suite-overview)
3. [BobClient SDK](#bobclient-sdk)
4. [LangGraph Integration](#langgraph-integration)
5. [Agent Integration Contracts](#agent-integration-contracts)
6. [Event Bus Integration](#event-bus-integration)
7. [Best Practices](#best-practices)
8. [Examples](#examples)

---

## Quick Start

### Installation

```bash
pip install bob-agent-tools
```

### Basic Usage

```python
from bob.tools import BobClient

# Initialize client
client = BobClient(
    base_url="http://bob-api:8000",
    api_key="your-api-key"
)

# Semantic search
results = client.semantic_search(
    query="authentication middleware",
    repo_id="550e8400-e29b-41d4-a716-446655440000",
    k=10
)

for result in results:
    print(f"{result.file_path}:{result.symbol_name} (confidence: {result.confidence})")
```

---

## Tool Suite Overview

Bob provides 10 tools for RuntimeOps agents:

| Tool | Purpose | Primary Users |
|------|---------|---------------|
| `semantic_search` | Find code by natural language query | Root Cause Agent |
| `resolve_stack_trace` | Map stack traces to file paths | Root Cause Agent |
| `get_dependency_graph` | Analyze code dependencies | All agents |
| `get_blast_radius` | Compute change impact | Dependency Agent |
| `get_file_content` | Retrieve file with metadata | Patch Agent |
| `get_commit_diff` | Analyze commit changes | Root Cause Agent |
| `get_test_map` | Find related tests | Test Agent |
| `get_conventions` | Get coding standards | Patch Agent |
| `get_risk_context` | Assess file risk | Risk Agent |
| `trigger_reindex` | Update repository index | Orchestrator |

---

## BobClient SDK

### Synchronous Usage

```python
from bob.tools import BobClient

with BobClient() as client:
    # Semantic search
    results = client.semantic_search(
        query="database connection pool",
        repo_id="550e8400-...",
        k=5
    )
    
    # Get dependency graph
    graph = client.get_dependency_graph(
        file_path="src/db/connection.py",
        repo_id="550e8400-...",
        hops=3,
        direction="both"
    )
    
    # Get blast radius
    blast_radius = client.get_blast_radius(
        files=["src/db/models/user.py"],
        repo_id="550e8400-..."
    )
```

### Asynchronous Usage

```python
import asyncio
from bob.tools import BobClient

async def analyze_incident():
    async with BobClient() as client:
        # Run queries concurrently
        results = await asyncio.gather(
            client.semantic_search_async("error handling", repo_id),
            client.get_dependency_graph_async("src/main.py", repo_id),
            client.get_risk_context_async(["src/main.py"], repo_id)
        )
        
        search_results, graph, risk_contexts = results
        return search_results, graph, risk_contexts

# Run async function
asyncio.run(analyze_incident())
```

### Error Handling

```python
from bob.tools import BobClient
from bob.exceptions import (
    QueryError,
    QueryTimeoutError,
    ResourceNotFoundError,
    AuthenticationError
)

client = BobClient()

try:
    content = client.get_file_content("src/main.py", repo_id)
except ResourceNotFoundError:
    print("File not found")
except QueryTimeoutError:
    print("Query timed out")
except AuthenticationError:
    print("Invalid API key")
except QueryError as e:
    print(f"Query failed: {e}")
```

---

## LangGraph Integration

### Creating Tool Definitions

```python
from bob.tools import create_bob_tools
from langgraph.prebuilt import ToolNode

# Create all Bob tools
bob_tools = create_bob_tools()

# Create LangGraph ToolNode
tool_node = ToolNode(bob_tools)
```

### Agent-Specific Toolsets

```python
from bob.tools import AgentToolset

# Root Cause Agent (3 tools)
root_cause_tools = AgentToolset.root_cause_agent_tools()

# Patch Agent (3 tools)
patch_tools = AgentToolset.patch_agent_tools()

# Test Agent (2 tools)
test_tools = AgentToolset.test_agent_tools()

# Dependency Agent (2 tools)
dependency_tools = AgentToolset.dependency_agent_tools()

# Risk Agent (2 tools)
risk_tools = AgentToolset.risk_agent_tools()

# Incident Orchestrator (2 tools)
orchestrator_tools = AgentToolset.incident_orchestrator_tools()
```

### State Management

```python
from bob.tools import BobStateManager

# Initialize state manager
state_manager = BobStateManager()

# Create snapshot for incident
snapshot_id = state_manager.create_snapshot(
    incident_id="INC-12345",
    repo_id="550e8400-..."
)

# Store Bob responses
state_manager.store_response(
    snapshot_id=snapshot_id,
    tool_name="bob_semantic_search",
    response=search_results,
    agent_name="root_cause_agent"
)

# Retrieve responses
responses = state_manager.get_responses(snapshot_id, "bob_semantic_search")

# Clear snapshot on resolution
state_manager.clear_snapshot(snapshot_id)
```

---

## Agent Integration Contracts

### Root Cause Agent

**Tools Used:**
- `bob_resolve_stack_trace`: Parse error stack traces
- `bob_semantic_search`: Find related code
- `bob_get_commit_diff`: Analyze recent changes

**Example Workflow:**

```python
from bob.tools import BobClient

client = BobClient()

# 1. Resolve stack trace
trace = """
Traceback (most recent call last):
  File "src/app.py", line 42, in handler
    process_request()
"""

frames = client.resolve_stack_trace(trace, repo_id)
error_file = frames[0].file_path

# 2. Search for related code
results = client.semantic_search(
    query="request processing error handling",
    repo_id=repo_id,
    k=5
)

# 3. Get recent commits
diff = client.get_commit_diff(
    commit_sha=frames[0].commit_sha,
    repo_id=repo_id
)
```

### Patch Agent

**Tools Used:**
- `bob_get_file_content`: Read source files
- `bob_get_dependency_graph`: Understand dependencies
- `bob_get_conventions`: Follow coding standards

**Example Workflow:**

```python
# 1. Get file content
content = client.get_file_content("src/auth.py", repo_id)

# 2. Analyze dependencies
graph = client.get_dependency_graph(
    file_path="src/auth.py",
    repo_id=repo_id,
    hops=2
)

# 3. Get conventions
conventions = client.get_conventions("services/auth", repo_id)

# Generate patch following conventions
patch = generate_patch(content, conventions)
```

### Test Agent

**Tools Used:**
- `bob_get_test_map`: Find related tests
- `bob_get_dependency_graph`: Understand test coverage

**Example Workflow:**

```python
# 1. Get test files
tests = client.get_test_map(
    source_files=["src/auth.py", "src/db.py"],
    repo_id=repo_id
)

# 2. Analyze test dependencies
for test_file in tests:
    graph = client.get_dependency_graph(test_file, repo_id)
```

### Dependency Agent

**Tools Used:**
- `bob_get_blast_radius`: Compute change impact
- `bob_get_dependency_graph`: Analyze coupling

**Example Workflow:**

```python
# 1. Compute blast radius
blast_radius = client.get_blast_radius(
    files=["src/db/models/user.py"],
    repo_id=repo_id
)

# 2. Analyze high-risk files
for file in blast_radius.impacted_files[:5]:
    if file.acs_score > 0.8:
        graph = client.get_dependency_graph(file.file_path, repo_id)
```

### Risk Agent

**Tools Used:**
- `bob_get_risk_context`: Assess file risk
- `bob_get_dependency_graph`: Understand impact

**Example Workflow:**

```python
# 1. Get risk context
risk_contexts = client.get_risk_context(
    files=["src/db/models/user.py", "src/api/auth.py"],
    repo_id=repo_id
)

# 2. Classify risk
for ctx in risk_contexts:
    if ctx.risk_level == "CRITICAL":
        # Require additional approvals
        pass
```

---

## Event Bus Integration

### Emitting Events

```python
from bob.tools import EventEmitter, EventType

emitter = EventEmitter(backend="redis")

# Emit index complete event
emitter.emit_index_complete(
    repo_id="550e8400-...",
    files_indexed=1234,
    duration_ms=5000.0
)

# Emit query executed event
emitter.emit_query_executed(
    repo_id="550e8400-...",
    query_type="semantic_search",
    duration_ms=150.0,
    result_count=10
)
```

### Subscribing to Events

```python
from bob.tools import EventSubscriber, EventType, BobEvent

subscriber = EventSubscriber(backend="redis")

# Register handler
def handle_incident(event: BobEvent):
    print(f"Incident: {event.data['incident_id']}")
    # Trigger analysis workflow

subscriber.register_handler(EventType.INCIDENT_INTAKE, handle_incident)

# Subscribe to events
subscriber.subscribe([
    EventType.INCIDENT_INTAKE,
    EventType.GITHUB_PUSH
])
```

### Event Bus Manager

```python
from bob.tools import EventBusManager

# Initialize manager (registers default handlers)
manager = EventBusManager(backend="redis")

# Start listening
manager.start_listening()
```

---

## Best Practices

### 1. Use Context Managers

```python
# Good: Automatic cleanup
with BobClient() as client:
    results = client.semantic_search(query, repo_id)

# Bad: Manual cleanup required
client = BobClient()
results = client.semantic_search(query, repo_id)
client.close()
```

### 2. Handle Errors Gracefully

```python
from bob.exceptions import QueryError

try:
    results = client.semantic_search(query, repo_id)
except QueryError as e:
    logger.error(f"Search failed: {e}")
    # Fallback to alternative approach
    results = []
```

### 3. Use Async for Concurrent Operations

```python
# Good: Concurrent queries
async with BobClient() as client:
    results = await asyncio.gather(
        client.semantic_search_async(query1, repo_id),
        client.semantic_search_async(query2, repo_id)
    )

# Bad: Sequential queries
results1 = client.semantic_search(query1, repo_id)
results2 = client.semantic_search(query2, repo_id)
```

### 4. Cache Expensive Operations

```python
# Cache conventions (24-hour TTL)
conventions = client.get_conventions(service_path, repo_id)

# Reuse for multiple files in same service
for file in service_files:
    patch = generate_patch(file, conventions)
```

### 5. Use State Management for Incidents

```python
# Create snapshot at incident start
snapshot_id = state_manager.create_snapshot(incident_id, repo_id)

# Store all agent responses
state_manager.store_response(snapshot_id, tool_name, response, agent_name)

# Clear on resolution
state_manager.clear_snapshot(snapshot_id)
```

---

## Examples

### Example 1: Root Cause Analysis

```python
from bob.tools import BobClient

async def analyze_error(stack_trace: str, repo_id: str):
    async with BobClient() as client:
        # 1. Resolve stack trace
        frames = await client.resolve_stack_trace_async(stack_trace, repo_id)
        
        # 2. Get error file
        error_file = frames[0].file_path
        
        # 3. Search for similar errors
        results = await client.semantic_search_async(
            query=f"error handling in {error_file}",
            repo_id=repo_id,
            k=5
        )
        
        # 4. Get recent changes
        if frames[0].commit_sha:
            diff = await client.get_commit_diff_async(
                frames[0].commit_sha,
                repo_id
            )
            
            return {
                "error_file": error_file,
                "similar_code": results,
                "recent_changes": diff
            }
```

### Example 2: Change Impact Analysis

```python
from bob.tools import BobClient

def analyze_change_impact(changed_files: list[str], repo_id: str):
    with BobClient() as client:
        # 1. Compute blast radius
        blast_radius = client.get_blast_radius(changed_files, repo_id)
        
        # 2. Get risk context for impacted files
        impacted_paths = [f.file_path for f in blast_radius.impacted_files]
        risk_contexts = client.get_risk_context(impacted_paths, repo_id)
        
        # 3. Find tests
        tests = client.get_test_map(changed_files, repo_id)
        
        return {
            "total_impacted": blast_radius.total_impacted,
            "high_risk_files": [
                ctx.file_path for ctx in risk_contexts
                if ctx.risk_level in ["HIGH", "CRITICAL"]
            ],
            "affected_services": blast_radius.affected_services,
            "test_files": tests
        }
```

### Example 3: Automated Patch Generation

```python
from bob.tools import BobClient

def generate_fix(file_path: str, repo_id: str):
    with BobClient() as client:
        # 1. Get file content
        content = client.get_file_content(file_path, repo_id)
        
        # 2. Get conventions
        service_path = "/".join(file_path.split("/")[:2])
        conventions = client.get_conventions(service_path, repo_id)
        
        # 3. Get dependencies
        graph = client.get_dependency_graph(
            file_path,
            repo_id,
            hops=2
        )
        
        # 4. Generate patch
        patch = create_patch(
            content=content.content,
            conventions=conventions,
            dependencies=graph.edges
        )
        
        return patch
```

---

## Support

For issues or questions:
- GitHub: https://github.com/ibm/bob
- Slack: #bob-support
- Email: bob-team@ibm.com

---

**Made with Bob** 🤖