#!/usr/bin/env python3
"""SciScope agentic terminal assistant.

Unlike `chat_cli.py` (fixed retrieval->answer), this drives the agent LOOP: the
local LLM autonomously calls tools (search / trends / recommend / graph) and then
synthesises a grounded answer. Tool calls are shown inline so you can see the
agent's reasoning steps.

Run:
    make agent          (or)    python scripts/agent_cli.py
"""

from __future__ import annotations

import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

os.environ.setdefault("SCISCOPE_DB_DSN", "postgresql://tim@localhost:5432/sciscope")
os.environ.setdefault("SCISCOPE_EMBEDDER_PATH", os.path.join(REPO, "models/embedder_local/multilingual-e5-base"))


def _on_event(kind: str, payload: dict) -> None:
    if kind == "tool_call":
        args = ", ".join(f"{k}={v}" for k, v in payload["args"].items())
        print(f"  \033[36m⚙ 调用 {payload['name']}({args})\033[0m")
    elif kind == "tool_result":
        preview = payload["result"].replace("\n", " ")[:90]
        print(f"  \033[90m← {preview}…\033[0m")


def main() -> None:
    from backend.app.agent.loop import run_agent, _detect_model

    model = _detect_model()
    if not model:
        print("⚠ 本地大模型未在 :8001 运行。请先在另一终端 `make llm`。")
        return
    print(f"SciScope 科研智能体(agent 模式)— 模型: {model}")
    print("自主调用 检索/趋势/推荐/图谱 工具作答。空行或 Ctrl-C 退出。\n")

    history: list[dict] = []
    while True:
        try:
            q = input("你> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nbye")
            break
        if not q:
            break
        try:
            result = run_agent(q, history=history, model=model, on_event=_on_event)
        except Exception as exc:  # noqa: BLE001
            print(f"[error] {exc}\n")
            continue
        answer = result["answer"]
        used = ", ".join(dict.fromkeys(t["name"] for t in result.get("tools_used", []))) or "无"
        print(f"\nAI> {answer}")
        print(f"\033[90m[工具: {used} · {result['steps']} 步]\033[0m\n")
        history.append({"role": "user", "content": q})
        history.append({"role": "assistant", "content": answer})
        history[:] = history[-8:]


if __name__ == "__main__":
    main()
