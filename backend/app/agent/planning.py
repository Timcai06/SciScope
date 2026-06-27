"""Planning helpers shared by the LangGraph runtime and legacy fallback."""

from __future__ import annotations

from backend.app.agent.llm import complete


META_PROMPTS = (
    "你好", "您好", "你是谁", "你是什么", "你能做什么", "你能干什么", "你会什么",
    "你还会什么", "还能做什么", "除了科研文献", "除了文献", "除了论文", "能力", "边界", "局限", "自我介绍",
    "介绍一下你", "怎么用", "如何使用", "帮助", "谢谢", "多谢", "再见",
    "hello", "hi ", "who are you", "what can you", "what else can you", "help", "thanks",
)

PLAN_MARKERS = (
    "对比", "比较", "区别", "差异", "相比", "异同", "综述", "研究现状", "概览",
    "趋势", "演进", "演变", "发展", "推荐", "关系", "哪些", "梳理", "总结", "现状",
    "vs", "versus", "compare", "review", "survey", "trend", "recommend",
)


def needs_plan(question: str) -> bool:
    q = question.strip().lower()
    if len(q) < 4 or any(marker in q for marker in META_PROMPTS):
        return False
    return any(marker in q for marker in PLAN_MARKERS) or len(question) >= 18


def parse_plan(text: str) -> list[str]:
    steps: list[str] = []
    for line in (text or "").splitlines():
        step = line.strip().lstrip("-*·•0123456789.、)（) ").strip()
        core = step.rstrip(":：").strip()
        if len(step) >= 3 and core and core.lower() not in ("计划", "plan", "步骤", "steps"):
            steps.append(step)
    return steps[:4]


def make_plan(question: str, model: str) -> list[str]:
    prompt = [
        {"role": "system", "content": "你是科研智能体的规划器,只输出执行步骤。"},
        {"role": "user", "content": (
            "把下面的科研问题拆成 2-4 个可执行步骤。每步只能使用以下内置工具之一,"
            "并写清用它检索/处理什么:\n"
            "search_literature(检索文献)、get_trends(研究趋势)、recommend_papers(相似推荐)、"
            "get_paper(论文详情)、summarize_field(领域综述)、compare_papers(论文对比)、"
            "query_knowledge_graph(知识图谱)、verify_claim(论断核查)。\n"
            "不要使用 Google Scholar、Web of Science 等外部工具。"
            "注意:recommend_papers/get_paper/compare_papers 依赖 paper_id,必须先安排一步 "
            "search_literature 才能拿到 id,不能直接对主题词调用它们。"
            "每行一步,只输出步骤本身,不要解释、不要编号前缀。\n\n"
            f"问题:{question}\n\n步骤:"
        )},
    ]
    try:
        return parse_plan(complete(prompt, model))
    except Exception:  # noqa: BLE001 - planning is best-effort
        return []
