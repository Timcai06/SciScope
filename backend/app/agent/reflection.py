"""Reflection and retry heuristics for SciScope agent runtimes."""

from __future__ import annotations

from backend.app.agent.llm import complete
from backend.app.agent.planning import META_PROMPTS


WEAK_ANSWER = (
    "没有找到", "未找到", "未检索到", "无法回答", "无法确定", "抱歉",
    "没有相关", "缺乏", "无相关信息", "i don't", "cannot find", "no relevant",
)


def reflect_reason(answer: str, tools_used: int, question: str) -> str | None:
    """Return a retry instruction for ungrounded or weak answers."""
    answer_lower = (answer or "").lower()
    question_lower = question.strip().lower()
    is_meta = len(question_lower) < 4 or any(marker in question_lower for marker in META_PROMPTS)
    if tools_used == 0 and not is_meta:
        return "你没有调用任何工具就回答了。请先用 search_literature 等工具检索证据,再据实回答。"
    if any(marker in answer_lower for marker in WEAK_ANSWER):
        return "上次检索证据不足。请换用不同的关键词(或英文术语)重新检索,再回答。"
    return None


def self_critique(question: str, answer: str, model: str) -> str | None:
    prompt = [
        {"role": "system", "content": "你是严格的审稿人,只输出 OK 或 RETRY。"},
        {"role": "user", "content": (
            f"问题:{question}\n\n回答:{answer}\n\n"
            "判断这个回答是否充分回答了问题、且关键论断都有文献证据支撑。"
            "若充分且有据,只回复 OK;否则回复「RETRY:」加一句话指出缺什么、该补检索什么。"
        )},
    ]
    try:
        output = complete(prompt, model).strip()
    except Exception:  # noqa: BLE001
        return None
    if output.upper().startswith("RETRY"):
        reason = output.split(":", 1)[-1].split("：", 1)[-1].strip()
        return reason or "回答证据不足,请补充检索后重答。"
    return None
