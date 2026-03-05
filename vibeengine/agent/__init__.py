"""Agent module - LLM-driven browser automation"""

from vibeengine.agent.service import Agent
from vibeengine.agent.views import AgentConfig, AgentHistory, ActionResult

__all__ = [
    "Agent",
    "AgentConfig",
    "AgentHistory",
    "ActionResult",
]
