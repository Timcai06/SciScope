#!/usr/bin/env python3
"""SciScope agentic terminal assistant (streaming, rich TUI).

Drives the agent LOOP: the local LLM autonomously calls tools (search / trends /
recommend / graph), streams its reasoning, and synthesises a grounded answer.
Tool calls are shown live as the agent decides them; the final answer streams in
token-by-token — the stream/act/observe loop the way OpenCode / Claude Code do it.

Run:
    make agent      (or)    python scripts/agent_cli.py
Requires `make llm` (tool-calling enabled) on :8001.
"""

from __future__ import annotations

import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

os.environ.setdefault("SCISCOPE_DB_DSN", "postgresql://tim@localhost:5432/sciscope")
os.environ.setdefault("SCISCOPE_EMBEDDER_PATH", os.path.join(REPO, "models/embedder_local/multilingual-e5-base"))

from rich.console import Console  # noqa: E402

console = Console()


def main() -> None:
    from backend.app.agent.loop import _detect_model, stream_agent

    model = _detect_model()
    if not model:
        console.print("[yellow]⚠ 本地大模型未在 :8001 运行。请先在另一终端 `make llm`。[/]")
        return
    console.print(f"[bold]SciScope 科研智能体[/] [dim](agent 模式 · {model})[/]")
    console.print("[dim]自主调用 检索/趋势/推荐/图谱 工具作答。空行或 Ctrl-C 退出。[/]\n")

    history: list[dict] = []
    while True:
        try:
            q = console.input("[bold green]你>[/] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\nbye")
            break
        if not q:
            break

        answer = ""
        in_answer = False
        used: list[str] = []
        try:
            for kind, payload in stream_agent(q, history=history, model=model):
                if kind == "tool_call":
                    args = ", ".join(f"{k}={v}" for k, v in payload["args"].items() if v not in (None, "", 0))
                    console.print(f"  [cyan]⚙ {payload['name']}[/]([dim]{args}[/])")
                    used.append(payload["name"])
                elif kind == "tool_result":
                    preview = payload["result"].replace("\n", " ")[:80]
                    console.print(f"  [dim]← {preview}…[/]")
                elif kind == "text":
                    if not in_answer:
                        console.print("[bold blue]AI>[/] ", end="")
                        in_answer = True
                    console.print(payload, end="", style="default")
                    answer += payload
                elif kind == "final":
                    if not in_answer and payload:
                        console.print(f"[bold blue]AI>[/] {payload}", end="")
                        answer = payload
        except Exception as exc:  # noqa: BLE001
            console.print(f"\n[red][error] {exc}[/]\n")
            continue

        tools_line = ", ".join(dict.fromkeys(used)) or "无"
        console.print(f"\n[dim][工具: {tools_line}][/]\n")
        history.append({"role": "user", "content": q})
        history.append({"role": "assistant", "content": answer})
        history[:] = history[-8:]


if __name__ == "__main__":
    main()
