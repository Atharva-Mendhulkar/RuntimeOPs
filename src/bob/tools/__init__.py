"""
IBM Bob - Tools Module
Agent-facing tool suite for RuntimeOps agents
"""

from bob.tools.bob_tools import (
    semantic_search,
    resolve_stack_trace,
    get_dependency_graph,
    get_blast_radius,
    get_file_content,
    get_commit_diff,
    get_test_map,
    get_conventions,
    get_risk_context,
    trigger_reindex,
)
from bob.tools.client import BobClient
from bob.tools.event_bus import (
    EventEmitter,
    EventSubscriber,
    EventType,
    BobEvent,
    EventBusManager,
)
from bob.tools.langgraph_integration import (
    create_bob_tools,
    AgentToolset,
    BobStateManager,
    create_tool_node,
)
from bob.tools.models import (
    CodeSearchResult,
    StackFrame,
    DependencyGraph,
    DependencyEdge,
    BlastRadiusResult,
    ImpactedFile,
    FileContent,
    FileSymbol,
    CommitDiff,
    ChangedFile,
    RiskContext,
)

__all__ = [
    # Tool functions
    "semantic_search",
    "resolve_stack_trace",
    "get_dependency_graph",
    "get_blast_radius",
    "get_file_content",
    "get_commit_diff",
    "get_test_map",
    "get_conventions",
    "get_risk_context",
    "trigger_reindex",
    # Client
    "BobClient",
    # Event bus
    "EventEmitter",
    "EventSubscriber",
    "EventType",
    "BobEvent",
    "EventBusManager",
    # LangGraph integration
    "create_bob_tools",
    "AgentToolset",
    "BobStateManager",
    "create_tool_node",
    # Models
    "CodeSearchResult",
    "StackFrame",
    "DependencyGraph",
    "DependencyEdge",
    "BlastRadiusResult",
    "ImpactedFile",
    "FileContent",
    "FileSymbol",
    "CommitDiff",
    "ChangedFile",
    "RiskContext",
]

# Made with Bob