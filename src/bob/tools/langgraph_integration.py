"""
IBM Bob - LangGraph Integration
Tool definitions and state management for LangGraph agents
"""

import logging
from typing import Any

from bob.tools.client import BobClient

logger = logging.getLogger(__name__)


# ============================================================================
# LangGraph Tool Definitions
# ============================================================================


def create_bob_tools(client: BobClient | None = None) -> list[dict[str, Any]]:
    """
    Create LangGraph-compatible tool definitions for all Bob tools.

    Args:
        client: Optional BobClient instance (creates new one if not provided)

    Returns:
        List of tool definitions compatible with LangGraph ToolNode

    Example:
        >>> from langgraph.prebuilt import ToolNode
        >>> bob_tools = create_bob_tools()
        >>> tool_node = ToolNode(bob_tools)
    """
    if client is None:
        client = BobClient()

    tools = [
        {
            "name": "bob_semantic_search",
            "description": (
                "Search code semantically across repository using natural language. "
                "Returns top-K code units (functions, classes) with confidence scores. "
                "Use for finding relevant code based on functionality description."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language search query (e.g., 'authentication middleware')",  # noqa: E501
                    },
                    "repo_id": {
                        "type": "string",
                        "description": "Repository UUID to search within",
                    },
                    "k": {
                        "type": "integer",
                        "description": "Number of results to return (default: 10, max: 50)",
                        "default": 10,
                    },
                },
                "required": ["query", "repo_id"],
            },
            "function": lambda query, repo_id, k=10: client.semantic_search(query, repo_id, k),
        },
        {
            "name": "bob_resolve_stack_trace",
            "description": (
                "Resolve stack trace to repository file paths with git blame info. "
                "Parses stack traces (Python, Java, JS, Go) and maps to actual files. "
                "Use for root cause analysis of errors and exceptions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "trace_text": {
                        "type": "string",
                        "description": "Raw stack trace text from error logs",
                    },
                    "repo_id": {
                        "type": "string",
                        "description": "Repository UUID",
                    },
                },
                "required": ["trace_text", "repo_id"],
            },
            "function": lambda trace_text, repo_id: client.resolve_stack_trace(trace_text, repo_id),
        },
        {
            "name": "bob_get_dependency_graph",
            "description": (
                "Retrieve file dependency graph within N hops. "
                "Returns adjacency list of import/dependency relationships. "
                "Use for understanding code coupling and impact analysis."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "File path to analyze",
                    },
                    "repo_id": {
                        "type": "string",
                        "description": "Repository UUID",
                    },
                    "hops": {
                        "type": "integer",
                        "description": "Number of hops to traverse (default: 3, max: 10)",
                        "default": 3,
                    },
                    "direction": {
                        "type": "string",
                        "enum": ["upstream", "downstream", "both"],
                        "description": "Traversal direction",
                        "default": "both",
                    },
                },
                "required": ["file_path", "repo_id"],
            },
            "function": lambda file_path, repo_id, hops=3, direction="both": client.get_dependency_graph(  # noqa: E501
                file_path, repo_id, hops, direction
            ),
        },
        {
            "name": "bob_get_blast_radius",
            "description": (
                "Compute blast radius for changed files. "
                "Returns all impacted files sorted by Architectural Criticality Score (ACS). "
                "Use for change impact analysis and risk assessment."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of changed file paths (max 100)",
                    },
                    "repo_id": {
                        "type": "string",
                        "description": "Repository UUID",
                    },
                },
                "required": ["files", "repo_id"],
            },
            "function": lambda files, repo_id: client.get_blast_radius(files, repo_id),
        },
        {
            "name": "bob_get_file_content",
            "description": (
                "Fetch file content with parsed metadata. "
                "Returns file content, symbols (functions/classes), and imports. "
                "Use for reading code files and understanding structure."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "File path relative to repository root",
                    },
                    "repo_id": {
                        "type": "string",
                        "description": "Repository UUID",
                    },
                },
                "required": ["file_path", "repo_id"],
            },
            "function": lambda file_path, repo_id: client.get_file_content(file_path, repo_id),
        },
        {
            "name": "bob_get_commit_diff",
            "description": (
                "Fetch git diff for commit with impact analysis. "
                "Returns changed files with dependency edges and linked tests. "
                "Use for understanding what changed in a commit."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "commit_sha": {
                        "type": "string",
                        "description": "Commit SHA (short or full)",
                    },
                    "repo_id": {
                        "type": "string",
                        "description": "Repository UUID",
                    },
                },
                "required": ["commit_sha", "repo_id"],
            },
            "function": lambda commit_sha, repo_id: client.get_commit_diff(commit_sha, repo_id),
        },
        {
            "name": "bob_get_test_map",
            "description": (
                "Get test files that import or reference source files. "
                "Uses naming conventions and import relationships. "
                "Use for finding tests related to changed code."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "source_files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of source file paths",
                    },
                    "repo_id": {
                        "type": "string",
                        "description": "Repository UUID",
                    },
                },
                "required": ["source_files", "repo_id"],
            },
            "function": lambda source_files, repo_id: client.get_test_map(source_files, repo_id),
        },
        {
            "name": "bob_get_conventions",
            "description": (
                "Get coding conventions for a service. "
                "Returns naming, error handling, and import order conventions. "
                "Use for generating code that follows project standards."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "service_path": {
                        "type": "string",
                        "description": "Service path (e.g., 'services/auth')",
                    },
                    "repo_id": {
                        "type": "string",
                        "description": "Repository UUID",
                    },
                },
                "required": ["service_path", "repo_id"],
            },
            "function": lambda service_path, repo_id: client.get_conventions(service_path, repo_id),
        },
        {
            "name": "bob_get_risk_context",
            "description": (
                "Get risk context for files. "
                "Returns ACS scores, downstream service counts, and incident history. "
                "Use for risk assessment and prioritization."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of file paths",
                    },
                    "repo_id": {
                        "type": "string",
                        "description": "Repository UUID",
                    },
                },
                "required": ["files", "repo_id"],
            },
            "function": lambda files, repo_id: client.get_risk_context(files, repo_id),
        },
        {
            "name": "bob_trigger_reindex",
            "description": (
                "Trigger repository reindexing. "
                "Enqueues an ingest job and returns job_id for status polling. "
                "Use when repository has been updated and needs re-analysis."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_id": {
                        "type": "string",
                        "description": "Repository UUID",
                    },
                    "scope": {
                        "type": "string",
                        "enum": ["incremental", "full"],
                        "description": "Reindex scope",
                        "default": "incremental",
                    },
                },
                "required": ["repo_id"],
            },
            "function": lambda repo_id, scope="incremental": client.trigger_reindex(repo_id, scope),
        },
    ]

    logger.info(f"Created {len(tools)} Bob tools for LangGraph")
    return tools


# ============================================================================
# Agent Integration Contracts
# ============================================================================


class AgentToolset:
    """
    Predefined tool subsets for specific agent types.

    Implements integration contracts from PRD Section 12.
    """

    @staticmethod
    def root_cause_agent_tools(client: BobClient | None = None) -> list[dict[str, Any]]:
        """
        Tools for Root Cause Agent.

        Uses: resolve_stack_trace, semantic_search, get_commit_diff
        """
        all_tools = create_bob_tools(client)
        tool_names = {
            "bob_resolve_stack_trace",
            "bob_semantic_search",
            "bob_get_commit_diff",
        }
        return [t for t in all_tools if t["name"] in tool_names]

    @staticmethod
    def patch_agent_tools(client: BobClient | None = None) -> list[dict[str, Any]]:
        """
        Tools for Patch Agent.

        Uses: get_file_content, get_dependency_graph, get_conventions
        """
        all_tools = create_bob_tools(client)
        tool_names = {
            "bob_get_file_content",
            "bob_get_dependency_graph",
            "bob_get_conventions",
        }
        return [t for t in all_tools if t["name"] in tool_names]

    @staticmethod
    def test_agent_tools(client: BobClient | None = None) -> list[dict[str, Any]]:
        """
        Tools for Test Agent.

        Uses: get_test_map, get_dependency_graph
        """
        all_tools = create_bob_tools(client)
        tool_names = {
            "bob_get_test_map",
            "bob_get_dependency_graph",
        }
        return [t for t in all_tools if t["name"] in tool_names]

    @staticmethod
    def dependency_agent_tools(client: BobClient | None = None) -> list[dict[str, Any]]:
        """
        Tools for Dependency Agent.

        Uses: get_blast_radius, get_dependency_graph
        """
        all_tools = create_bob_tools(client)
        tool_names = {
            "bob_get_blast_radius",
            "bob_get_dependency_graph",
        }
        return [t for t in all_tools if t["name"] in tool_names]

    @staticmethod
    def risk_agent_tools(client: BobClient | None = None) -> list[dict[str, Any]]:
        """
        Tools for Risk Agent.

        Uses: get_risk_context, get_dependency_graph
        """
        all_tools = create_bob_tools(client)
        tool_names = {
            "bob_get_risk_context",
            "bob_get_dependency_graph",
        }
        return [t for t in all_tools if t["name"] in tool_names]

    @staticmethod
    def incident_orchestrator_tools(client: BobClient | None = None) -> list[dict[str, Any]]:
        """
        Tools for Incident Orchestrator.

        Uses: trigger_reindex, health check (via semantic_search as proxy)
        """
        all_tools = create_bob_tools(client)
        tool_names = {
            "bob_trigger_reindex",
            "bob_semantic_search",  # Can be used for health check
        }
        return [t for t in all_tools if t["name"] in tool_names]


# ============================================================================
# State Management
# ============================================================================


class BobStateManager:
    """
    Manages Bob responses in LangGraph state.

    Provides immutable state snapshots for incident runs and ensures
    consistency across agent invocations.
    """

    def __init__(self):
        self.state_snapshots: dict[str, dict[str, Any]] = {}
        logger.info("BobStateManager initialized")

    def create_snapshot(self, incident_id: str, repo_id: str) -> str:
        """
        Create immutable state snapshot for incident run.

        Args:
            incident_id: Unique incident identifier
            repo_id: Repository UUID

        Returns:
            Snapshot ID
        """
        snapshot_id = f"{incident_id}:{repo_id}"

        self.state_snapshots[snapshot_id] = {
            "incident_id": incident_id,
            "repo_id": repo_id,
            "created_at": None,  # TODO: Add timestamp
            "bob_responses": {},
            "agent_invocations": [],
        }

        logger.info(f"Created state snapshot: {snapshot_id}")
        return snapshot_id

    def store_response(
        self,
        snapshot_id: str,
        tool_name: str,
        response: Any,
        agent_name: str,
    ) -> None:
        """
        Store Bob tool response in state snapshot.

        Args:
            snapshot_id: Snapshot identifier
            tool_name: Name of Bob tool invoked
            response: Tool response data
            agent_name: Name of agent that invoked tool
        """
        if snapshot_id not in self.state_snapshots:
            logger.warning(f"Snapshot not found: {snapshot_id}")
            return

        snapshot = self.state_snapshots[snapshot_id]

        # Store response
        if tool_name not in snapshot["bob_responses"]:
            snapshot["bob_responses"][tool_name] = []

        snapshot["bob_responses"][tool_name].append(
            {
                "response": response,
                "agent": agent_name,
                "timestamp": None,  # TODO: Add timestamp
            }
        )

        # Track invocation
        snapshot["agent_invocations"].append(
            {
                "agent": agent_name,
                "tool": tool_name,
                "timestamp": None,  # TODO: Add timestamp
            }
        )

        logger.debug(f"Stored response for {tool_name} in snapshot {snapshot_id}")

    def get_snapshot(self, snapshot_id: str) -> dict[str, Any] | None:
        """
        Retrieve immutable state snapshot.

        Args:
            snapshot_id: Snapshot identifier

        Returns:
            Snapshot data or None if not found
        """
        return self.state_snapshots.get(snapshot_id)

    def get_responses(
        self,
        snapshot_id: str,
        tool_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get Bob responses from snapshot.

        Args:
            snapshot_id: Snapshot identifier
            tool_name: Optional tool name filter

        Returns:
            List of responses
        """
        snapshot = self.state_snapshots.get(snapshot_id)
        if not snapshot:
            return []

        if tool_name:
            return snapshot["bob_responses"].get(tool_name, [])

        # Return all responses
        all_responses = []
        for responses in snapshot["bob_responses"].values():
            all_responses.extend(responses)
        return all_responses

    def clear_snapshot(self, snapshot_id: str) -> None:
        """
        Clear state snapshot (after incident resolution).

        Args:
            snapshot_id: Snapshot identifier
        """
        if snapshot_id in self.state_snapshots:
            del self.state_snapshots[snapshot_id]
            logger.info(f"Cleared state snapshot: {snapshot_id}")


# ============================================================================
# Helper Functions
# ============================================================================


def create_tool_node(agent_type: str, client: BobClient | None = None):
    """
    Create LangGraph ToolNode for specific agent type.

    Args:
        agent_type: Agent type (root_cause, patch, test, dependency, risk, orchestrator)
        client: Optional BobClient instance

    Returns:
        ToolNode configured with appropriate tools

    Example:
        >>> from langgraph.prebuilt import ToolNode
        >>> tool_node = create_tool_node("root_cause")
    """
    try:
        from langgraph.prebuilt import ToolNode
    except ImportError:
        logger.error("langgraph not installed. Install with: pip install langgraph")
        raise

    agent_toolsets = {
        "root_cause": AgentToolset.root_cause_agent_tools,
        "patch": AgentToolset.patch_agent_tools,
        "test": AgentToolset.test_agent_tools,
        "dependency": AgentToolset.dependency_agent_tools,
        "risk": AgentToolset.risk_agent_tools,
        "orchestrator": AgentToolset.incident_orchestrator_tools,
    }

    if agent_type not in agent_toolsets:
        raise ValueError(f"Unknown agent type: {agent_type}")

    tools = agent_toolsets[agent_type](client)
    logger.info(f"Created ToolNode for {agent_type} agent with {len(tools)} tools")

    return ToolNode(tools)


# Made with Bob
