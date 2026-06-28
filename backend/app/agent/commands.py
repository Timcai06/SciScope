"""Slash-command / skill registry — a Claude Code commands analog.

User-invocable commands (``/review``, ``/trend``, ``/verify`` …) are intercepted
before the LLM loop and dispatched to a handler that maps onto existing
capabilities (specialist sub-agents and tools). Mirrors Claude Code's command
system: a registry of named, self-describing commands dispatched by a leading
``/``; the registry is the single source of truth for ``/help``.

Backend-only by design — the Go TUI already gestures at "/ 调用命令", so it can
consume this through the agent stream without any change here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal


@dataclass(frozen=True)
class Command:
    """A user-invocable command. ``run`` takes the argument string after the name.

    ``kind`` decides what the runtime does with ``run``'s return value:
    * ``"answer"`` — the string is a final answer (e.g. /help, /search results).
    * ``"prompt"`` — the string is a skill-expanded prompt to run through the
      agent loop (e.g. /review, /trend), so a slash command behaves identically
      whether typed in the TUI or sent to the API.
    """

    name: str                       # without the leading slash
    description: str                # one-line "what it does", shown by /help
    run: Callable[[str], str]
    arg_hint: str = ""              # e.g. "<主题>", shown by /help
    kind: Literal["answer", "prompt"] = "answer"


_COMMANDS: dict[str, Command] = {}


def register_command(cmd: Command) -> None:
    _COMMANDS[cmd.name] = cmd


def list_commands() -> list[Command]:
    return list(_COMMANDS.values())


def parse_command(text: str) -> tuple[str, str] | None:
    """Split a leading-slash message into ``(name, argument)``; None if not a command."""
    s = (text or "").strip()
    if not s.startswith("/"):
        return None
    body = s[1:].strip()
    if not body:
        return ("help", "")
    head, _, rest = body.partition(" ")
    return (head.lower(), rest.strip())


def command_for(text: str) -> Command | None:
    """The Command a message invokes, or None when it is not a slash command.

    Note: an *unknown* slash command still counts as a command (returns the help
    command's sentinel via :func:`is_command`); callers use :func:`run_command`
    to get the actual response.
    """
    parsed = parse_command(text)
    if parsed is None:
        return None
    return _COMMANDS.get(parsed[0])


def is_command(text: str) -> bool:
    """Whether a message should be handled as a command (any leading-slash input)."""
    return parse_command(text) is not None


def run_command(text: str) -> str | None:
    """Dispatch a slash command. Returns None when ``text`` is not a command.

    An unknown command returns a helpful message (not None), so the caller still
    bypasses the LLM loop instead of sending "/foo" to the model.
    """
    parsed = parse_command(text)
    if parsed is None:
        return None
    name, arg = parsed
    cmd = _COMMANDS.get(name)
    if cmd is None:
        known = ", ".join("/" + c.name for c in _COMMANDS.values())
        return f"未知命令 /{name}。可用命令:{known}(/help 查看说明)"
    return cmd.run(arg)


# --- Built-in commands ------------------------------------------------------
def _help(_arg: str) -> str:
    lines = ["SciScope 可用命令:"]
    for cmd in _COMMANDS.values():
        hint = f" {cmd.arg_hint}" if cmd.arg_hint else ""
        lines.append(f"  /{cmd.name}{hint} — {cmd.description}")
    return "\n".join(lines)


def _skill(skill_name: str, usage: str):
    """A prompt command: expand a skill template with the user input (or show usage)."""

    def handler(arg: str) -> str:
        if not arg.strip():
            return usage
        from backend.app.agent.skills import render_skill_prompt

        return render_skill_prompt(skill_name, arg, fallback="请就以下内容完成研究任务:" + arg)

    return handler


def _search(arg: str) -> str:
    if not arg.strip():
        return "用法:/search <查询> — 在文献库中检索相关论文。"
    from backend.app.agent.tools import execute_tool

    return execute_tool("search_literature", {"query": arg})


def command_kind(text: str) -> str:
    """Whether a command produces a final answer or a prompt to run through the loop."""
    cmd = command_for(text)
    return cmd.kind if cmd else "answer"


def _register_builtins() -> None:
    register_command(Command("help", "列出所有可用命令", _help))
    register_command(Command("review", "就给定主题产出研究现状综述", _skill("literature-review", "用法:/review <主题> — 产出该主题的研究现状综述。"), "<主题>", kind="prompt"))
    register_command(Command("trend", "分析给定主题的研究趋势", _skill("trend-analysis", "用法:/trend <主题> — 分析该主题的研究趋势。"), "<主题>", kind="prompt"))
    register_command(Command("verify", "核查一句论断是否有文献支持", _skill("claim-check", "用法:/verify <论断> — 对该论断做证据接地核查。"), "<论断>", kind="prompt"))
    register_command(Command("recommend", "按主题或种子论文推荐论文", _skill("paper-recommendation", "用法:/recommend <主题或 paper_id> — 推荐后续阅读。"), "<主题|paper_id>", kind="prompt"))
    register_command(Command("search", "在文献库中检索相关论文", _search, "<查询>"))


_register_builtins()
