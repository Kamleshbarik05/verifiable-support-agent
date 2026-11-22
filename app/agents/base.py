"""
app/agents/base.py
Base agent abstraction compliant with Google Agent Development Kit (ADK) patterns.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from app.agents.state import AgentState


class BaseAgent(ABC):
    """
    Abstract base class for all ADK sub-agents in the support triage topology.
    """

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self.tools: list[Callable[..., Any]] = []

    def register_tool(self, tool_func: Callable[..., Any]):
        """Registers a tool callable with the agent."""
        self.tools.append(tool_func)

    @abstractmethod
    def process(self, state: AgentState) -> AgentState:
        """Executes agent task and transitions state."""
        pass
