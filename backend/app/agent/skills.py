"""SciScope skill catalog exposed to prompts and slash commands.

Skills are lightweight workflow recipes stored in ``.sciscope/skills``. They do
not add tools by themselves; they teach the model when and how to combine the
already registered agent tools for recurring research tasks.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SkillSummary:
    name: str
    description: str
    tools: tuple[str, ...]
    path: Path


def _repo_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".sciscope" / "skills").is_dir():
            return candidate
    return current


def skills_dir(start: Path | None = None) -> Path:
    return _repo_root(start) / ".sciscope" / "skills"


def _parse_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    meta: dict[str, str] = {}
    for line in parts[1].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip()
    return meta


def list_skill_summaries(start: Path | None = None) -> tuple[SkillSummary, ...]:
    directory = skills_dir(start)
    if not directory.is_dir():
        return ()

    summaries: list[SkillSummary] = []
    for path in sorted(directory.glob("*.md")):
        meta = _parse_frontmatter(path.read_text(encoding="utf-8"))
        name = meta.get("name") or path.stem
        tools = tuple(tool.strip() for tool in meta.get("tools", "").split(",") if tool.strip())
        summaries.append(
            SkillSummary(
                name=name,
                description=meta.get("description", ""),
                tools=tools,
                path=path,
            )
        )
    return tuple(summaries)


def skills_prompt(start: Path | None = None) -> str:
    summaries = list_skill_summaries(start)
    if not summaries:
        return ""

    lines: list[str] = []
    for skill in summaries:
        tool_hint = f" 建议工具: {', '.join(skill.tools)}。" if skill.tools else ""
        lines.append(f"- /{skill.name}: {skill.description}.{tool_hint}")
    return "\n".join(lines)
