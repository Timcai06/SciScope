"""delegate — hand a focused subtask to a specialist sub-agent."""

from __future__ import annotations

from typing import Any, Iterator

from backend.app.agent.tools.base import Tool

SCHEMA = {
    "type": "function",
    "function": {
        "name": "delegate",
        "description": (
            "把一个聚焦的子任务交给专员子智能体:role=reviewer(文献综述)/trend(趋势分析)/critic(论断核查)。"
            "仅在复杂、多面的任务需要分工时使用(如「综述 X 并核查其中关键论断」);简单问题请自己直接回答,不要滥用。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "role": {"type": "string", "description": "reviewer / trend / critic"},
                "task": {"type": "string", "description": "交给该专员的具体子任务(中文)"},
            },
            "required": ["role", "task"],
        },
    },
}


def run(args: dict[str, Any]) -> Iterator[str]:
    """Generator handler: announces the delegation, returns the specialist answer."""
    # Lazy import: specialists imports llm/tool_runner/tools, so defer to call time.
    from backend.app.agent.specialists import run_specialist

    role = str(args.get("role") or "").strip()
    yield f"委派子任务给专员: {role or '?'}…"
    return run_specialist(role, str(args.get("task") or ""))


TOOL = Tool(
    name="delegate",
    schema=SCHEMA,
    run=run,
    prompt_fragment="把聚焦子任务交给专员子智能体(reviewer/trend/critic),用于复杂多面任务的分工",
)
