"""Public entrypoint for the SciScope agent runtime.

The agent is orchestrated by a single LangGraph ``StateGraph`` (see
``langgraph_runtime``):

``prepare -> plan -> llm_step -> execute_tools -> reflect/force_synthesis -> END``.

This module is the stable import seam used by the API layer so HTTP routes never
depend on the concrete orchestrator module name.
"""

from __future__ import annotations

from backend.app.agent.langgraph_runtime import run_agent, stream_agent

__all__ = ["run_agent", "stream_agent"]
