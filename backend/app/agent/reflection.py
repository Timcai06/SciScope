"""Reflection and retry heuristics for SciScope agent runtimes."""

from __future__ import annotations

from backend.app.agent.llm import complete
from backend.app.agent.planning import META_PROMPTS


WEAK_ANSWER = (
    "没有找到", "未找到", "未检索到", "无法回答", "无法确定", "抱歉",
    "没有相关", "缺乏", "无相关信息", "i don't", "cannot find", "no relevant",
)

# Signals that a question is actually about the literature corpus and therefore
# should be grounded in tool-retrieved evidence. General/common-sense questions
# carry none of these and are allowed to be answered without calling tools.
LITERATURE_INTENT = (
    "论文", "文献", "综述", "趋势", "研究现状", "研究进展", "进展", "最新", "近年", "近期",
    "推荐", "作者", "引用", "发表", "期刊", "数据集", "对比", "比较",
    "知识图谱", "领域", "前沿", "sota", "state of the art",
    "paper", "literature", "research", "review", "survey", "trend",
    "recommend", "citation", "cite", "author", "dataset", "recent",
)

CAPABILITY_INTENT = (
    "你能做什么", "你能干什么", "你会什么", "你还会什么", "还能做什么",
    "除了科研文献", "除了文献", "除了论文", "能力", "边界", "局限", "限制", "怎么用", "如何使用",
    "what can you", "what else can you", "capability", "abilities", "limits",
)


def reflect_reason(answer: str, tools_used: int, question: str) -> str | None:
    """Return a retry instruction for ungrounded or weak answers.

    A tool-free answer is only pushed back when the question shows literature
    intent — common-sense / general questions legitimately need no tools.
    """
    answer_lower = (answer or "").lower()
    question_lower = question.strip().lower()
    is_meta = len(question_lower) < 4 or any(marker in question_lower for marker in META_PROMPTS)
    is_capability = any(marker in question_lower for marker in CAPABILITY_INTENT)
    needs_literature = any(marker in question_lower for marker in LITERATURE_INTENT)
    if tools_used == 0 and not is_meta and not is_capability and needs_literature:
        return "你没有调用任何工具就回答了。请先用 search_literature 等工具检索证据,再据实回答。"
    if any(marker in answer_lower for marker in WEAK_ANSWER):
        return "上次检索证据不足。请换用不同的关键词(或英文术语)重新检索,再回答。"
    return None


def self_critique(question: str, answer: str, model: str) -> str | None:
    prompt = [
        {"role": "system", "content": "你是严格的审稿人,只输出 OK 或 RETRY。"},
        {"role": "user", "content": (
            f"问题:{question}\n\n回答:{answer}\n\n"
            "判断这个回答是否正面回答了问题、且关键论断标注了出处(论文标题+年份即可;"
            "本系统以文献库内 paper_id 标识论文,不要求 DOI、期刊卷期或外部链接,缺这些不算缺陷)。"
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
