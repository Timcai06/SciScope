#!/usr/bin/env python3
"""SciScope agentic terminal assistant — streaming, themed rich TUI.

The local LLM autonomously calls tools (search / trends / recommend / graph /
paper), streams its answer token-by-token, and renders it as Markdown. Tool
steps show live with per-tool icons and a spinner — the stream/act/observe loop
with a polished terminal UI (OpenCode / Claude Code style).

Run:  make agent   (requires `make llm` with tool-calling on :8001)
"""

from __future__ import annotations

import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.environ.setdefault("SCISCOPE_DB_DSN", "postgresql://tim@localhost:5432/sciscope")
os.environ.setdefault("SCISCOPE_EMBEDDER_PATH", os.path.join(REPO, "models/embedder_local/multilingual-e5-base"))

from rich.console import Console  # noqa: E402
from rich.live import Live  # noqa: E402
from rich.markdown import Markdown  # noqa: E402
from rich.panel import Panel  # noqa: E402
from rich.rule import Rule  # noqa: E402
from rich.text import Text  # noqa: E402
from rich.theme import Theme  # noqa: E402

THEME = Theme(
    {
        "brand": "bold #5fd7ff",
        "accent": "#ff87d7",
        "muted": "grey54",
        "tool": "bold cyan",
        "toolarg": "grey62",
        "user": "bold green3",
        "ai": "#5fd7ff",
        "hint": "grey42",
    }
)
console = Console(theme=THEME)

ICONS = {
    "search_literature": "🔍",
    "get_trends": "📈",
    "recommend_papers": "📚",
    "query_knowledge_graph": "🕸️",
    "get_paper": "📄",
}
LABELS = {
    "search_literature": "检索文献",
    "get_trends": "研究趋势",
    "recommend_papers": "论文推荐",
    "query_knowledge_graph": "知识图谱",
    "get_paper": "论文详情",
}


def _banner(model: str) -> None:
    body = Text()
    body.append("🔬 SciScope 科研智能体\n", style="brand")
    body.append("自主调用 检索 · 趋势 · 推荐 · 图谱 · 取文 等工具,据实作答\n", style="muted")
    body.append(f"模型 {model}", style="hint")
    console.print(Panel(body, border_style="brand", expand=False, padding=(0, 2)))
    console.print("[hint]输入问题开始;空行或 Ctrl-C 退出。[/]\n")


def main() -> None:
    from backend.app.agent.loop import _detect_model, stream_agent

    model = _detect_model()
    if not model:
        console.print(Panel("[accent]本地大模型未在 :8001 运行。[/]\n请在另一终端先运行 [tool]make llm[/]",
                            border_style="accent", title="⚠ 未就绪"))
        return
    _banner(model)

    history: list[dict] = []
    while True:
        try:
            q = console.input("[user]❯[/] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[muted]再见[/]")
            break
        if not q:
            break

        answer = ""
        used: list[str] = []
        live: Live | None = None
        status = console.status("[muted]思考中…[/]", spinner="dots")
        status.start()
        try:
            for kind, payload in stream_agent(q, history=history, model=model):
                if kind == "tool_call":
                    status.stop()
                    name = payload["name"]
                    icon, label = ICONS.get(name, "⚙"), LABELS.get(name, name)
                    args = " · ".join(str(v) for v in payload["args"].values() if v not in (None, "", 0))
                    console.print(f"  {icon} [tool]{label}[/] [toolarg]{args}[/]")
                    used.append(name)
                    status = console.status(f"[muted]{label}运行中…[/]", spinner="dots")
                    status.start()
                elif kind == "tool_result":
                    pass  # results feed the model; keep the UI clean
                elif kind == "text":
                    if live is None:
                        status.stop()
                        live = Live(console=console, refresh_per_second=12, transient=True)
                        live.start()
                    answer += payload
                    live.update(Text(answer, style="ai"))
                elif kind == "final":
                    if not answer:
                        answer = payload
        except Exception as exc:  # noqa: BLE001
            if live:
                live.stop()
            status.stop()
            console.print(f"[accent][错误][/] {exc}\n")
            continue
        finally:
            if live:
                live.stop()
            status.stop()

        # Settle the streamed text into a polished Markdown panel.
        footer = "  ".join(f"{ICONS.get(n,'⚙')} {LABELS.get(n,n)}" for n in dict.fromkeys(used)) or "直接回答"
        console.print(
            Panel(Markdown(answer or "(无回答)"), border_style="ai", title="[ai]回答[/]",
                  subtitle=f"[hint]{footer}[/]", padding=(1, 2))
        )
        console.print(Rule(style="hint"))
        history.append({"role": "user", "content": q})
        history.append({"role": "assistant", "content": answer})
        history[:] = history[-8:]


if __name__ == "__main__":
    main()
