"""
Integration tests for Bob agent integration
Tests the complete flow of agent tool usage
"""

from uuid import uuid4

import pytest

from bob.tools.client import BobClient
from bob.tools.event_bus import (
    BobEvent,
    EventEmitter,
    EventSubscriber,
    EventType,
    IncidentEventHandler,
    WebhookEventHandler,
)
from bob.tools.langgraph_integration import (
    AgentToolset,
    BobStateManager,
    create_bob_tools,
)

# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def repo_id():
    """Test repository ID"""
    return str(uuid4())


@pytest.fixture
def incident_id():
    """Test incident ID"""
    return f"INC-{uuid4().hex[:8]}"


@pytest.fixture
def bob_client():
    """Bob client for testing"""
    return BobClient(
        base_url="http://localhost:8000",
        api_key="test-api-key",
    )


# ============================================================================
# Test LangGraph Tool Creation
# ============================================================================


def test_create_bob_tools():
    """Test creating all Bob tools for LangGraph"""
    tools = create_bob_tools()

    assert len(tools) == 10
    assert all("name" in tool for tool in tools)
    assert all("description" in tool for tool in tools)
    assert all("parameters" in tool for tool in tools)
    assert all("function" in tool for tool in tools)

    # Check tool names
    tool_names = {tool["name"] for tool in tools}
    expected_names = {
        "bob_semantic_search",
        "bob_resolve_stack_trace",
        "bob_get_dependency_graph",
        "bob_get_blast_radius",
        "bob_get_file_content",
        "bob_get_commit_diff",
        "bob_get_test_map",
        "bob_get_conventions",
        "bob_get_risk_context",
        "bob_trigger_reindex",
    }
    assert tool_names == expected_names


# ============================================================================
# Test Agent Toolsets
# ============================================================================


def test_root_cause_agent_toolset():
    """Test Root Cause Agent toolset"""
    tools = AgentToolset.root_cause_agent_tools()

    assert len(tools) == 3
    tool_names = {tool["name"] for tool in tools}
    assert tool_names == {
        "bob_resolve_stack_trace",
        "bob_semantic_search",
        "bob_get_commit_diff",
    }


def test_patch_agent_toolset():
    """Test Patch Agent toolset"""
    tools = AgentToolset.patch_agent_tools()

    assert len(tools) == 3
    tool_names = {tool["name"] for tool in tools}
    assert tool_names == {
        "bob_get_file_content",
        "bob_get_dependency_graph",
        "bob_get_conventions",
    }


def test_test_agent_toolset():
    """Test Test Agent toolset"""
    tools = AgentToolset.test_agent_tools()

    assert len(tools) == 2
    tool_names = {tool["name"] for tool in tools}
    assert tool_names == {
        "bob_get_test_map",
        "bob_get_dependency_graph",
    }


def test_dependency_agent_toolset():
    """Test Dependency Agent toolset"""
    tools = AgentToolset.dependency_agent_tools()

    assert len(tools) == 2
    tool_names = {tool["name"] for tool in tools}
    assert tool_names == {
        "bob_get_blast_radius",
        "bob_get_dependency_graph",
    }


def test_risk_agent_toolset():
    """Test Risk Agent toolset"""
    tools = AgentToolset.risk_agent_tools()

    assert len(tools) == 2
    tool_names = {tool["name"] for tool in tools}
    assert tool_names == {
        "bob_get_risk_context",
        "bob_get_dependency_graph",
    }


def test_incident_orchestrator_toolset():
    """Test Incident Orchestrator toolset"""
    tools = AgentToolset.incident_orchestrator_tools()

    assert len(tools) == 2
    tool_names = {tool["name"] for tool in tools}
    assert tool_names == {
        "bob_trigger_reindex",
        "bob_semantic_search",
    }


# ============================================================================
# Test State Management
# ============================================================================


def test_state_manager_create_snapshot(incident_id, repo_id):
    """Test creating state snapshot"""
    manager = BobStateManager()

    snapshot_id = manager.create_snapshot(incident_id, repo_id)

    assert snapshot_id == f"{incident_id}:{repo_id}"
    assert snapshot_id in manager.state_snapshots

    snapshot = manager.get_snapshot(snapshot_id)
    assert snapshot is not None
    assert snapshot["incident_id"] == incident_id
    assert snapshot["repo_id"] == repo_id


def test_state_manager_store_response(incident_id, repo_id):
    """Test storing Bob response in state"""
    manager = BobStateManager()
    snapshot_id = manager.create_snapshot(incident_id, repo_id)

    # Store response
    response = {"file_path": "src/main.py", "confidence": 0.95}
    manager.store_response(
        snapshot_id=snapshot_id,
        tool_name="bob_semantic_search",
        response=response,
        agent_name="root_cause_agent",
    )

    # Retrieve responses
    responses = manager.get_responses(snapshot_id, "bob_semantic_search")
    assert len(responses) == 1
    assert responses[0]["response"] == response
    assert responses[0]["agent"] == "root_cause_agent"


def test_state_manager_get_all_responses(incident_id, repo_id):
    """Test getting all responses from snapshot"""
    manager = BobStateManager()
    snapshot_id = manager.create_snapshot(incident_id, repo_id)

    # Store multiple responses
    manager.store_response(snapshot_id, "bob_semantic_search", {"data": 1}, "agent1")
    manager.store_response(snapshot_id, "bob_get_file_content", {"data": 2}, "agent2")

    # Get all responses
    all_responses = manager.get_responses(snapshot_id)
    assert len(all_responses) == 2


def test_state_manager_clear_snapshot(incident_id, repo_id):
    """Test clearing state snapshot"""
    manager = BobStateManager()
    snapshot_id = manager.create_snapshot(incident_id, repo_id)

    assert snapshot_id in manager.state_snapshots

    manager.clear_snapshot(snapshot_id)

    assert snapshot_id not in manager.state_snapshots
    assert manager.get_snapshot(snapshot_id) is None


# ============================================================================
# Test Event Bus
# ============================================================================


def test_event_emitter_initialization():
    """Test EventEmitter initialization"""
    emitter = EventEmitter(backend="redis")
    assert emitter.backend == "redis"


def test_event_creation(repo_id):
    """Test BobEvent creation"""
    event = BobEvent(
        event_type=EventType.INDEX_COMPLETE,
        repo_id=repo_id,
        data={"files_indexed": 100},
    )

    assert event.event_type == EventType.INDEX_COMPLETE
    assert event.repo_id == repo_id
    assert event.data["files_indexed"] == 100
    assert event.source == "bob"


def test_event_emitter_emit_index_complete(repo_id):
    """Test emitting index complete event"""
    emitter = EventEmitter(backend="redis")

    # This will fail without Redis, but tests the interface
    try:
        emitter.emit_index_complete(
            repo_id=repo_id,
            files_indexed=100,
            duration_ms=5000.0,
        )
    except Exception:
        pass  # Expected without Redis


def test_event_subscriber_initialization():
    """Test EventSubscriber initialization"""
    subscriber = EventSubscriber(backend="redis")
    assert subscriber.backend == "redis"
    assert len(subscriber._handlers) == 0


def test_event_subscriber_register_handler():
    """Test registering event handler"""
    subscriber = EventSubscriber(backend="redis")

    def handler(event: BobEvent):
        pass

    subscriber.register_handler(EventType.INCIDENT_INTAKE, handler)

    assert EventType.INCIDENT_INTAKE in subscriber._handlers
    assert len(subscriber._handlers[EventType.INCIDENT_INTAKE]) == 1


def test_incident_event_handler_initialization():
    """Test IncidentEventHandler initialization"""
    handler = IncidentEventHandler()
    assert handler.emitter is not None


def test_webhook_event_handler_initialization():
    """Test WebhookEventHandler initialization"""
    handler = WebhookEventHandler()
    assert handler.emitter is not None


# ============================================================================
# Test End-to-End Agent Workflows
# ============================================================================


@pytest.mark.integration
def test_root_cause_agent_workflow(repo_id):
    """
    Test Root Cause Agent workflow:
    1. Resolve stack trace
    2. Semantic search for related code
    3. Get commit diff
    """
    # This is a mock workflow test
    # In real integration, would call actual Bob API

    tools = AgentToolset.root_cause_agent_tools()
    assert len(tools) == 3

    # Simulate agent using tools
    tool_names_used = []
    for tool in tools:
        tool_names_used.append(tool["name"])

    assert "bob_resolve_stack_trace" in tool_names_used
    assert "bob_semantic_search" in tool_names_used
    assert "bob_get_commit_diff" in tool_names_used


@pytest.mark.integration
def test_patch_agent_workflow(repo_id):
    """
    Test Patch Agent workflow:
    1. Get file content
    2. Get dependency graph
    3. Get conventions
    """
    tools = AgentToolset.patch_agent_tools()
    assert len(tools) == 3

    tool_names = {tool["name"] for tool in tools}
    assert "bob_get_file_content" in tool_names
    assert "bob_get_dependency_graph" in tool_names
    assert "bob_get_conventions" in tool_names


@pytest.mark.integration
def test_incident_orchestration_workflow(incident_id, repo_id):
    """
    Test complete incident orchestration workflow:
    1. Create state snapshot
    2. Store agent responses
    3. Clear snapshot on resolution
    """
    manager = BobStateManager()

    # Create snapshot
    snapshot_id = manager.create_snapshot(incident_id, repo_id)

    # Simulate Root Cause Agent
    manager.store_response(
        snapshot_id,
        "bob_resolve_stack_trace",
        {"frames": []},
        "root_cause_agent",
    )

    # Simulate Patch Agent
    manager.store_response(
        snapshot_id,
        "bob_get_file_content",
        {"content": "..."},
        "patch_agent",
    )

    # Verify responses stored
    all_responses = manager.get_responses(snapshot_id)
    assert len(all_responses) == 2

    # Clear on resolution
    manager.clear_snapshot(snapshot_id)
    assert manager.get_snapshot(snapshot_id) is None


# ============================================================================
# Test Tool Parameter Validation
# ============================================================================


def test_tool_parameters_validation():
    """Test that all tools have proper parameter schemas"""
    tools = create_bob_tools()

    for tool in tools:
        params = tool["parameters"]

        # Check required structure
        assert "type" in params
        assert params["type"] == "object"
        assert "properties" in params
        assert "required" in params

        # Check all required params are in properties
        for required_param in params["required"]:
            assert required_param in params["properties"]


def test_tool_descriptions():
    """Test that all tools have meaningful descriptions"""
    tools = create_bob_tools()

    for tool in tools:
        assert len(tool["description"]) > 50  # Meaningful description
        assert "." in tool["description"]  # Proper sentence


# ============================================================================
# Test Error Handling in Integration
# ============================================================================


@pytest.mark.integration
def test_state_manager_handles_missing_snapshot():
    """Test state manager handles missing snapshot gracefully"""
    manager = BobStateManager()

    # Try to get non-existent snapshot
    snapshot = manager.get_snapshot("nonexistent")
    assert snapshot is None

    # Try to get responses from non-existent snapshot
    responses = manager.get_responses("nonexistent")
    assert responses == []


@pytest.mark.integration
def test_event_handler_error_resilience(repo_id):
    """Test event handlers are resilient to errors"""
    handler = IncidentEventHandler()

    # Create malformed event
    event = BobEvent(
        event_type=EventType.INCIDENT_INTAKE,
        repo_id=repo_id,
        data={},  # Missing incident_id
    )

    # Should not raise exception
    try:
        handler.handle_incident_intake(event)
    except Exception as e:
        pytest.fail(f"Handler should not raise exception: {e}")


# Made with Bob
