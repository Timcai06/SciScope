"""Context compaction service — a Claude Code autoCompact / microCompact analog.

The agent loop appends tool results and turns to a running message list; left
unchecked it blows the model's context window (small on the local 7B) and inflates
cost. This service keeps the list within a token budget with two tiers, mirroring
Claude Code:

* **microcompact** (cheap, no LLM): keep the most recent ``keep_recent`` tool
  results in full and content-clear older large ones. Token-budget triggered.
* **autocompact** (one LLM call): when still far over budget, summarize the older
  middle turns into a single summary message, preserving the system prompt and the
  most recent turns.

Both return a :class:`CompactionResult` with before/after token telemetry and the
strategy applied, so the runtime can surface context/cost decisions. Token
estimation lives here too (Claude Code's tokenEstimation service) so the loop and
the compactor share one estimator.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

CLEAR_NOTE = " …(旧工具结果已压缩)"
SUMMARY_PREFIX = "【早前对话摘要】"


def estimate_tokens(text: str) -> int:
    """Rough token estimate (CJK ~1.5 chars/token, else ~4) for budget/telemetry.

    An estimate, labeled as such (mirrors Claude Code's tokenCountWithEstimation
    fallback). With a cloud provider it tracks billable volume closely enough to
    surface per-query cost and to drive compaction.
    """
    if not text:
        return 0
    cjk = sum(1 for ch in text if "一" <= ch <= "鿿")
    return int(cjk / 1.5 + (len(text) - cjk) / 4)


def messages_tokens(messages: list[dict]) -> int:
    return sum(estimate_tokens(str(m.get("content") or "")) for m in messages)


@dataclass
class CompactionResult:
    """Telemetry for one compaction pass."""

    strategy: str  # "none" | "microcompact" | "autocompact"
    tokens_before: int
    tokens_after: int
    tool_results_cleared: int = 0
    messages_summarized: int = 0

    @property
    def tokens_freed(self) -> int:
        return max(self.tokens_before - self.tokens_after, 0)


def microcompact(
    messages: list[dict],
    *,
    token_budget: int = 4000,
    keep_recent: int = 2,
    min_clear_chars: int = 400,
) -> CompactionResult:
    """Clear old tool results in place, keeping the most recent ``keep_recent``.

    No-op (and returns ``strategy="none"``) when already under budget. Only large
    tool results are cleared, so short results and assistant/user turns are kept.
    """
    before = messages_tokens(messages)
    if before <= token_budget:
        return CompactionResult("none", before, before)

    tool_indices = [i for i, m in enumerate(messages) if m.get("role") == "tool"]
    keep = set(tool_indices[-keep_recent:]) if keep_recent > 0 else set()
    cleared = 0
    for i in tool_indices:
        if i in keep:
            continue
        content = str(messages[i].get("content") or "")
        if len(content) > min_clear_chars:
            messages[i]["content"] = content[:min_clear_chars] + CLEAR_NOTE
            cleared += 1
    after = messages_tokens(messages)
    return CompactionResult(
        "microcompact" if cleared else "none", before, after, tool_results_cleared=cleared
    )


def autocompact(
    messages: list[dict],
    summarize: Callable[[str], str],
    *,
    token_budget: int = 6000,
    keep_recent_msgs: int = 4,
    max_transcript_chars_per_msg: int = 1200,
) -> CompactionResult:
    """Summarize the older middle turns into one message, in place.

    Preserves a leading system message and the last ``keep_recent_msgs`` messages;
    replaces everything between with a single summary produced by ``summarize``
    (injected so this stays testable and free of a hard LLM dependency). No-op when
    under budget or when there is nothing in the middle to summarize.
    """
    before = messages_tokens(messages)
    if before <= token_budget:
        return CompactionResult("none", before, before)

    head = 1 if messages and messages[0].get("role") == "system" else 0
    recent = messages[len(messages) - keep_recent_msgs:] if keep_recent_msgs > 0 else []
    middle = messages[head: len(messages) - len(recent)]
    if not middle:
        return CompactionResult("none", before, before)

    transcript = "\n".join(
        f"{m.get('role')}: {str(m.get('content') or '')[:max_transcript_chars_per_msg]}" for m in middle
    )
    summary = summarize(transcript)
    messages[:] = messages[:head] + [{"role": "user", "content": SUMMARY_PREFIX + summary}] + recent
    after = messages_tokens(messages)
    return CompactionResult("autocompact", before, after, messages_summarized=len(middle))


def compact(messages: list[dict], *, token_budget: int = 4000, keep_recent: int = 2) -> CompactionResult:
    """Default cheap compaction pass (microcompact). Mutates ``messages`` in place."""
    return microcompact(messages, token_budget=token_budget, keep_recent=keep_recent)
