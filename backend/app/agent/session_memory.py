"""Session memory — persist salient facts across turns (Claude Code SessionMemory).

A small JSON-backed store keyed by session id. The agent recalls a compact memory
summary at the start of a turn (so it remembers the user's research focus and
prior findings) and records durable facts as the conversation goes. Cheap facts
(the user's research focus) are recorded with no LLM cost; richer extraction can
use the injected summarizer in :func:`extract_and_remember`, keeping the store
testable and LLM-optional.

Storage location is ``$SCISCOPE_AGENT_MEMORY_DIR`` (default ``data/.agent_memory``,
gitignored). Recall/remember are no-ops without a session id.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable

MEMORY_DIR_ENV = "SCISCOPE_AGENT_MEMORY_DIR"
DEFAULT_DIR = "data/.agent_memory"
MAX_MEMORIES = 12


def _memory_dir() -> Path:
    return Path(os.getenv(MEMORY_DIR_ENV, DEFAULT_DIR))


def _path(session_id: str) -> Path:
    safe = "".join(c for c in session_id if c.isalnum() or c in "-_") or "default"
    return _memory_dir() / f"{safe}.json"


def recall(session_id: str | None) -> list[str]:
    """Return remembered facts for a session (most recent last), or []."""
    if not session_id:
        return []
    path = _path(session_id)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return list(data.get("memories", []))[-MAX_MEMORIES:]
    except (json.JSONDecodeError, OSError):
        return []


def remember(session_id: str | None, *facts: str) -> list[str]:
    """Append new facts (deduped, capped) for a session; return the stored list."""
    cleaned = [f.strip() for f in facts if f and f.strip()]
    if not session_id or not cleaned:
        return recall(session_id)
    merged = recall(session_id)
    for fact in cleaned:
        if fact not in merged:
            merged.append(fact)
    merged = merged[-MAX_MEMORIES:]
    path = _path(session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"memories": merged}, ensure_ascii=False, indent=2), encoding="utf-8")
    return merged


def recall_prompt(session_id: str | None) -> str:
    """A compact system-prompt block of remembered facts, or "" when none."""
    memories = recall(session_id)
    if not memories:
        return ""
    return "已知该用户的研究背景与历史(供参考,不要复述给用户):\n" + "\n".join(f"- {m}" for m in memories)


def extract_and_remember(
    session_id: str | None,
    question: str,
    answer: str,
    summarize: Callable[[str, str], str],
) -> list[str]:
    """Distill 1-2 durable facts from a finished turn via ``summarize`` and store them.

    ``summarize(question, answer) -> str`` is injected (the LLM in production, a
    stub in tests) so this module never hard-depends on a model.
    """
    if not session_id:
        return []
    distilled = (summarize(question, answer) or "").strip()
    facts = [line.lstrip("-·* ").strip() for line in distilled.splitlines() if line.strip()][:2]
    return remember(session_id, *facts) if facts else recall(session_id)
