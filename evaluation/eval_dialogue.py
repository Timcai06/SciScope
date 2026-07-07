"""Dialogue-quality regression eval — replay real failure scenarios end to end.

维护口径说明:
- 这是**在线评测**:驱动真实 agent 链路(LLM provider + PostgreSQL + 本地 embedder),
  与 eval_all 的离线评测分开维护,不进 CI、不进 `make eval-all`。
- 每个场景的检查点都锚定一次真实体验中踩过的坑(2026-07 体验运行),用于防止
  提示词/反思层/工具层改动把已修复的问题改回去。LLM 输出有随机性,检查只断言
  行为中枢(调了什么工具、有没有强制重试、结论方向),不锁具体措辞。
- 判定通过 ≠ 对话质量好;判定失败 = 大概率回归,需人工看 transcript 复核。

Produces output/eval/dialogue_report.json + dialogue_report.md.

Usage:
    DEEPSEEK_API_KEY=... SCISCOPE_USE_MOCK_LLM=false SCISCOPE_LLM_PROVIDER=deepseek \
    SCISCOPE_DB_DSN=... SCISCOPE_EMBEDDER_PATH=... python -m evaluation.eval_dialogue
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

OUT_DIR = Path("output/eval")

# Transition narration that leaked into final answers before it was banned.
NARRATION_PHRASES = ("综合作答", "证据已足够", "证据充分了", "数据已全部返回", "现在综合")


@dataclass
class TurnRecord:
    """Everything one agent turn produced, flattened for checks."""

    question: str
    final: str = ""
    tool_calls: list[dict] = field(default_factory=list)  # {"name","args"}
    tool_results: list[dict] = field(default_factory=list)  # {"name","result"}
    reflects: list[str] = field(default_factory=list)
    seconds: float = 0.0

    def called(self, tool: str) -> list[dict]:
        return [c for c in self.tool_calls if c.get("name") == tool]

    def results_of(self, tool: str) -> str:
        return "\n".join(str(r.get("result")) for r in self.tool_results if r.get("name") == tool)


Check = tuple[str, Callable[[TurnRecord], bool]]


@dataclass(frozen=True)
class Case:
    case_id: str
    question: str
    checks: tuple[Check, ...]
    history: tuple[dict, ...] = ()
    pinned_from: str = ""  # which real failure this guards


def _no_narration(rec: TurnRecord) -> bool:
    head = rec.final[:80]
    return not any(phrase in head for phrase in NARRATION_PHRASES)


def _cites_papers(rec: TurnRecord) -> bool:
    return "《" in rec.final and "(20" in rec.final.replace("（", "(")


_REFERENCE_HISTORY = (
    {"role": "user", "content": "多跳推理有哪些代表性 RAG 论文?"},
    {
        "role": "assistant",
        "content": (
            "多跳推理 RAG 代表论文:\n"
            "1. **Plan*RAG** — 《Plan*RAG: Efficient Test-Time Planning for Retrieval "
            "Augmented Generation》(2024)\n"
            "2. **HopRAG** — 《HopRAG: Multi-Hop Reasoning for Logic-Aware "
            "Retrieval-Augmented Generation》(2025)\n"
            "3. **BRIEF** — 《BRIEF: Bridging Retrieval and Inference for Multi-hop "
            "Reasoning via Compression》(2024)"
        ),
    },
)

CASES: tuple[Case, ...] = (
    Case(
        case_id="reference-resolution",
        question="你刚才提到的第 2 篇论文具体做了什么?",
        history=_REFERENCE_HISTORY,
        pinned_from="规划器看不到历史,生成了 get_paper(paper_id='2')",
        checks=(
            ("不编造序号 paper_id", lambda r: not any(
                str(c.get("args", {}).get("paper_id", "")).strip() in {"1", "2", "3", "HopRAG"}
                for c in r.called("get_paper")
            )),
            ("回答落在 HopRAG 上", lambda r: "HopRAG" in r.final),
        ),
    ),
    Case(
        case_id="claim-honesty",
        question="求证:大语言模型会加剧学术不端。",
        pinned_from="反思层把「证据不足」逼成「明确支持」(确认偏误)",
        checks=(
            ("调用了 verify_claim", lambda r: bool(r.called("verify_claim"))),
            ("诚实判定未被强制重试", lambda r: not r.reflects),
            ("回答带引用", _cites_papers),
            ("verdict 与回答方向一致", lambda r: (
                "证据不足" not in r.results_of("verify_claim")
                or "明确支持" not in r.final[:60]
            )),
        ),
    ),
    Case(
        case_id="trend-faithful",
        question="图神经网络的研究趋势如何?",
        pinned_from="get_trends 返回 falling,回答却写成增长阶段",
        checks=(
            ("调用了 get_trends", lambda r: bool(r.called("get_trends"))),
            ("不显著趋势不说成显著上升", lambda r: (
                "不显著" not in r.results_of("get_trends") or "显著上升" not in r.final
            )),
            ("无过渡旁白", _no_narration),
        ),
    ),
    Case(
        case_id="boundary-2027",
        question="2027 年有哪些新论文?",
        pinned_from="语料时间边界(收录至 2026)",
        checks=(
            ("说明收录边界 2026", lambda r: "2026" in r.final),
            ("简短(<300 字)", lambda r: len(r.final) < 300),
        ),
    ),
    Case(
        case_id="vague-question",
        question="帮我看看",
        pinned_from="模糊问题曾盲搜 8 次工具调用烧光预算",
        checks=(
            ("不盲搜(0 次工具调用)", lambda r: not r.tool_calls),
            ("反问澄清", lambda r: ("?" in r.final or "？" in r.final)),
        ),
    ),
    Case(
        case_id="common-sense",
        question="什么是注意力机制?",
        pinned_from="常识问题不必检索",
        checks=(
            ("零工具调用", lambda r: not r.tool_calls),
            ("直接作答(非空)", lambda r: len(r.final) > 50),
        ),
    ),
    Case(
        case_id="survey-discipline",
        question="RAG 检索增强生成最近有哪些研究进展?",
        pinned_from="综述回答 1700+ 字、旁白开头、结尾总结段",
        checks=(
            ("带引用", _cites_papers),
            ("无过渡旁白", _no_narration),
            ("长度受控(<1800 字)", lambda r: len(r.final) < 1800),
        ),
    ),
)


def _run_case(case: Case) -> dict:
    from backend.app.agent.runtime import stream_agent

    rec = TurnRecord(question=case.question)
    started = time.perf_counter()
    for event in stream_agent(
        case.question, history=list(case.history), session_id=f"eval-dialogue-{case.case_id}"
    ):
        kind, payload, *_ = event
        if kind == "tool_call" and isinstance(payload, dict):
            rec.tool_calls.append(payload)
        elif kind == "tool_result" and isinstance(payload, dict):
            rec.tool_results.append(payload)
        elif kind == "reflect":
            rec.reflects.append(str(payload))
        elif kind == "final":
            rec.final = str(payload)
    rec.seconds = round(time.perf_counter() - started, 1)

    checks = [
        {"name": name, "passed": bool(predicate(rec))} for name, predicate in case.checks
    ]
    return {
        "case_id": case.case_id,
        "pinned_from": case.pinned_from,
        "passed": all(c["passed"] for c in checks),
        "checks": checks,
        "seconds": rec.seconds,
        "answer_chars": len(rec.final),
        "tool_calls": [c.get("name") for c in rec.tool_calls],
        "reflects": len(rec.reflects),
        "answer": rec.final,
    }


def run() -> dict:
    results = []
    for case in CASES:
        try:
            results.append(_run_case(case))
        except Exception as exc:  # keep evaluating remaining cases on one failure
            results.append({
                "case_id": case.case_id,
                "pinned_from": case.pinned_from,
                "passed": False,
                "checks": [],
                "error": f"{type(exc).__name__}: {exc}",
            })
        print(f"[{results[-1]['case_id']}] {'PASS' if results[-1]['passed'] else 'FAIL'}", flush=True)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cases_total": len(results),
        "cases_passed": sum(1 for r in results if r["passed"]),
        "results": results,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "dialogue_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT_DIR / "dialogue_report.md").write_text(_to_markdown(report), encoding="utf-8")
    return report


def _to_markdown(report: dict) -> str:
    lines = [
        "# SciScope 对话质量回归评测",
        "",
        f"生成时间:{report['generated_at']}",
        f"通过:**{report['cases_passed']}/{report['cases_total']}**",
        "",
        "| 场景 | 结果 | 锚定的真实问题 | 耗时 | 字数 |",
        "|---|---|---|---|---|",
    ]
    for r in report["results"]:
        mark = "✅" if r["passed"] else "❌"
        lines.append(
            f"| {r['case_id']} | {mark} | {r.get('pinned_from', '')} "
            f"| {r.get('seconds', '-')}s | {r.get('answer_chars', '-')} |"
        )
    lines.append("")
    for r in report["results"]:
        if r["passed"]:
            continue
        lines.append(f"## ❌ {r['case_id']}")
        if r.get("error"):
            lines.append(f"- 运行错误: {r['error']}")
        for c in r.get("checks", []):
            lines.append(f"- {'✅' if c['passed'] else '❌'} {c['name']}")
        if r.get("answer"):
            lines.append(f"\n回答全文:\n\n> {r['answer'][:800]}")
        lines.append("")
    lines.append("---")
    lines.append("*复现:`make eval-dialogue`(需 DeepSeek key + PostgreSQL + 本地 embedder;在线评测,不进 CI)。*")
    return "\n".join(lines)


if __name__ == "__main__":
    report = run()
    print(f"passed {report['cases_passed']}/{report['cases_total']}")
    print("written: output/eval/dialogue_report.json, output/eval/dialogue_report.md")
