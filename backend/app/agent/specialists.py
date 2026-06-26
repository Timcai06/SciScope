"""Specialist sub-agents (multi-agent, MCP/agent roadmap direction ③).

The main agent can delegate a focused subtask to a role-specialized sub-agent via
the ``delegate`` tool. Each specialist runs a bounded tool loop with its own
system prompt and a restricted tool subset — mirroring Claude Code's AgentTool
(directory-declared sub-agents spawned like a tool call).

Recursion is structurally impossible: the specialist tool subsets never include
``delegate``, so a sub-agent cannot spawn further sub-agents.
"""

from __future__ import annotations

from backend.app.agent.llm import complete, detect_model, drain, stream_chat
from backend.app.agent.tool_runner import run_tools
from backend.app.agent.tools import TOOL_SCHEMAS

MAX_SUB_STEPS = 3

SPECIALISTS: dict[str, dict] = {
    "reviewer": {
        "label": "综述员",
        "tools": ["search_literature", "summarize_field", "get_paper"],
        "prompt": (
            "你是文献综述专员。只做一件事:就给定主题检索代表论文,产出一段结构化的"
            "研究现状综述(方法流派、代表工作、局限),用中文,关键结论附论文标题为出处。不要跑题。"
        ),
    },
    "trend": {
        "label": "趋势分析师",
        "tools": ["get_trends", "search_literature"],
        "prompt": (
            "你是研究趋势分析专员。只分析给定主题的研究趋势:增长方向、阶段、预测及其依据,"
            "用中文解释趋势含义,不要罗列内部指标名。不要跑题。"
        ),
    },
    "critic": {
        "label": "批判核查员",
        "tools": ["verify_claim", "search_literature"],
        "prompt": (
            "你是批判性核查专员。对给定论断用 verify_claim 做证据接地核查,给出支持等级与出处,"
            "并指出论断中夸大或缺乏依据之处。用中文,克制、严谨。不要跑题。"
        ),
    },
}


def specialist_roles() -> list[str]:
    return list(SPECIALISTS)


def run_specialist(role: str, task: str) -> str:
    """Run one specialist sub-agent on a focused task; return its synthesized answer."""
    spec = SPECIALISTS.get(role)
    if spec is None:
        return f"未知专员角色: {role}(可用: {', '.join(SPECIALISTS)})"
    task = (task or "").strip()
    if not task:
        return f"delegate: 给 {spec['label']} 的任务为空"
    model = detect_model()
    if not model:
        return "生成模型不可用(请设置 DEEPSEEK_API_KEY 或 `make llm`)。"

    schemas = [s for s in TOOL_SCHEMAS if s["function"]["name"] in spec["tools"]]
    messages = [
        {"role": "system", "content": spec["prompt"]},
        {"role": "user", "content": task},
    ]
    executed: dict[str, str] = {}
    for _ in range(MAX_SUB_STEPS):
        full_text, tool_calls = drain(stream_chat(messages, model, schemas), lambda kind, payload: None)
        if not tool_calls:
            return full_text
        messages.append({"role": "assistant", "content": full_text, "tool_calls": tool_calls})
        for call, result in zip(tool_calls, run_tools(tool_calls, executed)):
            messages.append({"role": "tool", "tool_call_id": call.get("id", call["function"]["name"]), "content": result})
    messages.append({"role": "user", "content": "请基于以上证据给出最终结论。"})
    return complete(messages, model)
