#!/usr/bin/env python3
"""SciScope agentic terminal assistant — Claude Code-style rich TUI.

The local LLM autonomously calls tools (search / trends / recommend / graph /
paper / summarize / compare / bibliography), streams its answer token-by-token as
Markdown, and shows tool steps live. Slash commands (/help /tools /history /clear
/export /quit) provide a polished REPL.

Run:  make agent   (requires `make llm` with tool-calling on :8001)
"""

from __future__ import annotations

import os
import sys
from datetime import datetime

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.environ.setdefault("SCISCOPE_DB_DSN", "postgresql://tim@localhost:5432/sciscope")
os.environ.setdefault("SCISCOPE_EMBEDDER_PATH", os.path.join(REPO, "models/embedder_local/multilingual-e5-base"))

from rich.align import Align  # noqa: E402
from rich.console import Console, Group  # noqa: E402
from rich.live import Live  # noqa: E402
from rich.markdown import Markdown  # noqa: E402
from rich.panel import Panel  # noqa: E402
from rich.table import Table  # noqa: E402
from rich.text import Text  # noqa: E402
from rich.theme import Theme  # noqa: E402

# Claude Code-style palette: one warm accent, semantic colors, lots of muted grey.
THEME = Theme(
    {
        "brand": "bold #d7875f",      # warm terracotta accent (Claude-ish)
        "accent": "#d7875f",
        "accent2": "#5fafd7",          # cool secondary
        "muted": "grey50",
        "faint": "grey35",
        "ok": "green3",
        "warn": "yellow3",
        "err": "red3",
        "tool": "bold #5fafd7",
        "toolarg": "grey58",
        "user": "bold #87d787",
        "ai": "default",
        "rule": "grey30",
    }
)
console = Console(theme=THEME)

TOOLS = {
    "search_literature": ("🔍", "检索文献"),
    "get_trends": ("📈", "研究趋势"),
    "recommend_papers": ("📚", "论文推荐"),
    "get_paper": ("📄", "论文详情"),
    "summarize_field": ("📝", "领域综述"),
    "compare_papers": ("⚖️", "论文对比"),
    "export_bibliography": ("🔖", "引文导出"),
    "query_knowledge_graph": ("🕸️", "知识图谱"),
    "verify_claim": ("✅", "论断核查"),
}
HELP = [
    ("/help", "显示帮助"),
    ("/tools", "列出可用工具"),
    ("/history", "查看本轮对话历史"),
    ("/clear", "清空对话与屏幕"),
    ("/export", "导出对话到 Markdown 文件"),
    ("/model", "显示当前模型"),
    ("/quit", "退出 (或 Ctrl-C)"),
]


def banner(model: str) -> None:
    title = Text("✦ SciScope 科研智能体", style="brand")
    sub = Text("\n检索 · 趋势 · 推荐 · 图谱 · 综述 · 对比 · 引文 — 自主编排,据实作答", style="muted")
    tip = Text(f"\n\n输入问题,或 /help 看命令      模型 {model}", style="faint")
    console.print(Panel(Group(title, sub, tip), border_style="accent", padding=(1, 3), title="[faint]agent[/]"))


def status_line(model: str, turns: int) -> Text:
    t = Text()
    t.append("  ", style="")
    t.append("● ", style="ok")
    t.append(f"{model}", style="faint")
    t.append("   │   ", style="rule")
    t.append(f"对话 {turns} 轮", style="faint")
    t.append("   │   ", style="rule")
    t.append("/help 命令  ·  Ctrl-C 退出", style="faint")
    return t


def show_help() -> None:
    tbl = Table(show_header=False, box=None, padding=(0, 2, 0, 1))
    tbl.add_column(style="accent2", no_wrap=True)
    tbl.add_column(style="muted")
    for cmd, desc in HELP:
        tbl.add_row(cmd, desc)
    console.print(Panel(tbl, title="[brand]命令[/]", border_style="rule", padding=(1, 2)))


def show_tools() -> None:
    tbl = Table(show_header=False, box=None, padding=(0, 2, 0, 1))
    tbl.add_column(no_wrap=True)
    tbl.add_column(style="muted")
    for name, (icon, label) in TOOLS.items():
        tbl.add_row(f"{icon} [tool]{label}[/]", name)
    console.print(Panel(tbl, title="[brand]可用工具(LLM 自主调用)[/]", border_style="rule", padding=(1, 2)))


def show_history(history: list[dict]) -> None:
    if not history:
        console.print("[muted]  (暂无历史)[/]")
        return
    for m in history:
        who = "[user]你[/]" if m["role"] == "user" else "[accent]AI[/]"
        console.print(f"  {who} [faint]·[/] {m['content'][:100]}")


def export_chat(history: list[dict]) -> None:
    if not history:
        console.print("[warn]  无对话可导出。[/]")
        return
    fn = f"sciscope_chat_{datetime.now():%Y%m%d_%H%M%S}.md"
    path = os.path.join(REPO, "output", fn)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lines = ["# SciScope 对话记录\n"]
    for m in history:
        lines.append(f"## {'你' if m['role']=='user' else 'AI'}\n\n{m['content']}\n")
    open(path, "w", encoding="utf-8").write("\n".join(lines))
    console.print(f"[ok]  ✓ 已导出 → output/{fn}[/]")


def handle_slash(cmd: str, history: list[dict], model: str) -> bool:
    """Return True if input was a slash command (handled here)."""
    c = cmd.lower().strip()
    if c in ("/help", "/h", "/?"):
        show_help()
    elif c in ("/tools", "/t"):
        show_tools()
    elif c in ("/history", "/hist"):
        show_history(history)
    elif c in ("/clear", "/cls"):
        history.clear()
        console.clear()
        banner(model)
    elif c in ("/export", "/save"):
        export_chat(history)
    elif c == "/model":
        console.print(f"[muted]  当前模型:[/] [accent]{model}[/]")
    elif c in ("/quit", "/exit", "/q"):
        raise KeyboardInterrupt
    else:
        console.print(f"[warn]  未知命令 {cmd};/help 查看可用命令。[/]")
    return True


def run_turn(q: str, history: list[dict], model: str) -> None:
    from backend.app.agent.loop import stream_agent

    answer, used, live = "", [], None
    status = console.status("[muted]思考中…[/]", spinner="dots")
    status.start()
    try:
        for kind, payload in stream_agent(q, history=history, model=model):
            if kind == "tool_call":
                status.stop()
                icon, label = TOOLS.get(payload["name"], ("⚙", payload["name"]))
                args = " · ".join(str(v) for v in payload["args"].values() if v not in (None, "", 0))
                console.print(f"  [tool]{icon} {label}[/]  [toolarg]{args}[/]")
                used.append(payload["name"])
                status = console.status(f"[muted]{label}运行中…[/]", spinner="dots")
                status.start()
            elif kind == "plan":
                status.stop()
                console.print("  [tool]🗺 执行计划[/]")
                for i, step in enumerate(payload, 1):
                    console.print(f"     [faint]{i}.[/] [toolarg]{step}[/]")
                status = console.status("[muted]按计划执行…[/]", spinner="dots")
                status.start()
            elif kind == "reflect":
                if live:
                    live.stop(); live = None
                answer = ""
                console.print(f"  [warn]🔄 自我纠错[/] [faint]{payload[:46]}…[/]")
                status = console.status("[muted]重新检索…[/]", spinner="dots")
                status.start()
            elif kind == "text":
                if live is None:
                    status.stop()
                    live = Live(console=console, refresh_per_second=12, transient=True)
                    live.start()
                answer += payload
                live.update(Text(answer, style="ai"))
            elif kind == "final" and not answer:
                answer = payload
    except Exception as exc:  # noqa: BLE001
        if live:
            live.stop()
        status.stop()
        console.print(f"[err]  ✗ 出错:{exc}[/]\n")
        return
    finally:
        if live:
            live.stop()
        status.stop()

    footer = "  ".join(f"{TOOLS.get(n, ('⚙', n))[0]} {TOOLS.get(n, ('⚙', n))[1]}" for n in dict.fromkeys(used)) or "直接回答"
    console.print(
        Panel(Markdown(answer or "_(无回答)_"), border_style="accent",
              title="[accent]✦ 回答[/]", title_align="left",
              subtitle=f"[faint]{footer}[/]", subtitle_align="right", padding=(1, 2))
    )
    history.append({"role": "user", "content": q})
    history.append({"role": "assistant", "content": answer})
    del history[:-12]


def main() -> None:
    from backend.app.agent.loop import _detect_model

    model = _detect_model()
    if not model:
        console.print(Panel("[err]本地大模型未在 :8001 运行[/]\n\n请在另一终端先运行 [tool]make llm[/]",
                            border_style="err", title="⚠ 未就绪", padding=(1, 2)))
        return
    short = model.rsplit("/", 1)[-1]
    console.clear()
    banner(short)

    history: list[dict] = []
    while True:
        console.print(status_line(short, len(history) // 2), highlight=False)
        try:
            q = console.input("[accent]❯[/] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[muted]再见 ✦[/]")
            break
        if not q:
            continue
        if q.startswith("/"):
            try:
                handle_slash(q, history, short)
            except KeyboardInterrupt:
                console.print("\n[muted]再见 ✦[/]")
                break
            continue
        run_turn(q, history, model)


if __name__ == "__main__":
    main()
