"""L3 stance judge — evidence sentences, confidence/calibration, qualification.

This is the core of the 国赛 evidence layer (WB2). It upgrades verify_claim from
"an LLM labels whole evidence blocks" to a judgement that carries:

- ``sentence``: the verbatim evidence sentence supporting/contradicting the
  claim (evidence-sentence localisation; the smallest defensible span).
- ``confidence``: the judge's self-reported 0..1 probability per evidence,
  which the caller uses for calibrated aggregation and rejection (low
  confidence -> 证据不足, never a confident verdict).
- ``qualification``: qualifier-mismatch hints (population / dose / time /
  species / target), used to downgrade evidence that is topically similar but
  not actually about the claim's scope.

Contract: ``judge_evidence(claim, evidence_texts)`` returns ``JudgeResult``.
``ok=False`` means the judge was unavailable or unparseable — callers MUST NOT
derive a confident verdict; the similarity-only path may only say 证据不足
(fallback discipline).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

_STANCE_LABELS = {"SUPPORT", "CONTRADICT", "NEUTRAL"}

JUDGE_VERSION = "l3-1"


@dataclass
class EvidenceJudgement:
    stance: str
    confidence: float
    sentence: str
    qualification: str | None


@dataclass
class JudgeResult:
    ok: bool
    judgements: list[EvidenceJudgement] = field(default_factory=list)
    note: str = ""


def _coerce_judgements(raw: object, count: int) -> list[EvidenceJudgement]:
    """Coerce parsed LLM output into count-aligned judgements.

    Unknown stance labels become NEUTRAL; unparseable confidence becomes 0.5;
    missing sentence/qualification become empty/None. Never raises.
    """
    out: list[EvidenceJudgement] = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                item = {}
            stance = str(item.get("stance") or "NEUTRAL").strip().upper()
            if stance not in _STANCE_LABELS:
                stance = "NEUTRAL"
            try:
                conf = float(item.get("confidence", 0.5))
            except (TypeError, ValueError):
                conf = 0.5
            out.append(
                EvidenceJudgement(
                    stance=stance,
                    confidence=max(0.0, min(1.0, conf)),
                    sentence=str(item.get("sentence") or "").strip(),
                    qualification=(str(item["qualification"]).strip() or None)
                    if item.get("qualification")
                    else None,
                )
            )
    out = (out + [EvidenceJudgement("NEUTRAL", 0.5, "", None)] * count)[:count]
    return out


def _judge_prompt(claim: str, evidence_texts: list[str]) -> str:
    numbered = "\n".join(f"[{i}] {t}" for i, t in enumerate(evidence_texts))
    return (
        "你是严格的科学论断核查员。下面是一句论断和若干条文献证据。\n"
        "对每一条证据,输出一个对象,包含四个字段:\n"
        "- stance:该证据与论断的关系,只能取 SUPPORT(支持)/ CONTRADICT(表明论断为假或相反)/ NEUTRAL(无关或不足以判断);\n"
        "- confidence:你对该立场判定的置信度,0 到 1 之间的小数(校准标准:0.9 表示几乎确定,0.6 表示勉强可判,低于 0.5 视为不可判);\n"
        "- sentence:证据中直接支撑该立场的原句,逐字引用;若没有具体句子则填空字符串;\n"
        "- qualification:如果该证据的适用条件(人群/物种/剂量/时间/目标/任务)与论断隐含范围不一致,写一句简短提示;一致或无则填 null。\n"
        "只依据证据本身判断,不要用常识补足;论断与证据可能语言不同,按语义判断。\n\n"
        f"论断:{claim}\n证据:\n{numbered}\n\n"
        f"只输出一个 JSON 数组,长度必须为 {len(evidence_texts)},元素按证据顺序排列,"
        '例如 [{"stance":"SUPPORT","confidence":0.9,"sentence":"...","qualification":null}]。'
        "不要输出数组以外的任何内容。"
    )


def judge_evidence(claim: str, evidence_texts: list[str]) -> JudgeResult:
    """Ask the LLM judge for per-evidence L3 judgements.

    Returns ``JudgeResult(ok=False)`` when the judge is unavailable or the reply
    cannot be parsed — callers must fall back to the similarity-only path, which
    is only allowed to conclude 证据不足.
    """
    if not evidence_texts:
        return JudgeResult(ok=False, judgements=[], note="no evidence")
    from backend.app.services.deepseek_provider import get_llm_provider

    try:
        raw = get_llm_provider().complete(_judge_prompt(claim, evidence_texts))
        start, end = raw.find("["), raw.rfind("]")
        if start == -1 or end == -1:
            return JudgeResult(ok=False, judgements=[], note="unparseable reply")
        parsed = json.loads(raw[start : end + 1])
        if not isinstance(parsed, list):
            return JudgeResult(ok=False, judgements=[], note="reply is not a list")
    except Exception:  # noqa: BLE001 — judge unavailability is a normal offline state
        return JudgeResult(ok=False, judgements=[], note="judge unavailable")

    judgements = _coerce_judgements(parsed, len(evidence_texts))
    fixed = sum(1 for j in judgements if j.stance == "NEUTRAL")
    note = f"coerced {len(evidence_texts) - fixed} nonstandard labels" if fixed else ""
    return JudgeResult(ok=True, judgements=judgements, note=note)


def qualification_conflicts(judgements: list[EvidenceJudgement]) -> list[str]:
    """Qualifier hints on SUPPORT/CONTRADICT evidence, in evidence order."""
    return [j.qualification for j in judgements if j.qualification]


def validate_evidence_sentences(
    judgements: list[EvidenceJudgement], evidence_texts: list[str]
) -> list[EvidenceJudgement]:
    """Reject non-neutral labels without a verbatim, supplied evidence sentence.

    LLM output is untrusted: a plausible-looking rationale is not evidence unless
    its reported sentence appears in the exact evidence text passed to the judge.
    The row remains visible as a neutral, unaccepted result so callers can explain
    why it did not contribute to a stance verdict.
    """
    validated: list[EvidenceJudgement] = []
    for judgement, text in zip(judgements, evidence_texts):
        sentence = judgement.sentence.strip()
        if judgement.stance != "NEUTRAL" and (not sentence or sentence not in text):
            qualification = judgement.qualification or "未返回可在原始证据中核验的证据句"
            validated.append(EvidenceJudgement("NEUTRAL", 0.0, "", qualification))
        else:
            validated.append(judgement)
    return validated
