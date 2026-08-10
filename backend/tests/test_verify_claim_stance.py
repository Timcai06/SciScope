"""verify_claim L3: stance + confidence + evidence sentences + fallback discipline.

Step 0 pinned the defect (cosine grading is symmetric to negation, so both
landed "强支持"). Step 1 added a stance layer. WB2 (国赛 L3) adds:

- evidence-sentence localisation and per-evidence confidence,
- calibrated rejection: low-confidence or qualifier-mismatched evidence cannot
  drive a confident verdict (默认证据不足),
- fallback discipline: when the LLM judge is unavailable, the similarity-only
  path may ONLY conclude 证据不足 — never 强支持/部分支持.

The LLM judge (`verify_claim._judge_stances`) is mocked so tests stay offline
and deterministic: the claim reads SUPPORT(0.95), its negation CONTRADICT(0.95)
from the same papers — exactly the case cosine could not tell apart.
"""

from __future__ import annotations

import json
import math
from types import SimpleNamespace

import pytest

from backend.app.agent.tools import verify_claim
from backend.app.services.stance import judge as stance_judge

# A claim the (fake) literature supports, and its direct negation. Both are about
# the same topic, so a real retriever returns the same papers for either.
CLAIM = "咖啡能降低心脏病风险"
NEGATION = "咖啡会增加心脏病风险"

# Top claim<->evidence cosine each lands at — both clear the old 0.84 "强支持"
# bar, which is why similarity alone (Step 0) could not separate them.
_TOP_SIM = {CLAIM: 0.90, NEGATION: 0.88}


class _FakeEmbedder:
    """Embeds into R^2 so claim<->evidence dot product is a chosen value."""

    def __init__(self, top_sim: dict[str, float]) -> None:
        self._top_sim = top_sim

    def encode_query(self, text: str) -> list[float]:
        s = self._top_sim[text]
        return [s, math.sqrt(1.0 - s * s)]

    def encode_passages(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]


def _fake_search(query: str, limit: int = 6):
    """A claim and its negation are topically identical → same papers back."""
    return [
        SimpleNamespace(
            paper_id="W1",
            title="Coffee consumption and cardiovascular outcomes",
            snippet="A cohort study associating coffee intake with lower CVD risk.",
            year=2023,
        )
    ]


def _judgement(stance: str, confidence: float = 0.95, sentence: str = "", qualification: str | None = None):
    return stance_judge.EvidenceJudgement(
        stance=stance, confidence=confidence, sentence=sentence, qualification=qualification
    )


def _fake_judge(claim: str, evidence_texts: list[str]) -> stance_judge.JudgeResult:
    """SUPPORT for the claim, CONTRADICT for its negation — high confidence."""
    stance = "SUPPORT" if claim == CLAIM else "CONTRADICT"
    sentence = "A cohort study associating coffee intake with lower CVD risk."
    return stance_judge.JudgeResult(
        ok=True,
        judgements=[_judgement(stance, 0.95, sentence)],
        note="",
    )


@pytest.fixture
def _patched(monkeypatch: pytest.MonkeyPatch) -> list[tuple]:
    from backend.app.services import retrieval_service
    from backend.app.services.stance import store as stance_store
    from src.models import embeddings

    monkeypatch.setattr(retrieval_service, "search", _fake_search)
    monkeypatch.setattr(embeddings, "get_embedder", lambda *_a, **_k: _FakeEmbedder(_TOP_SIM))
    monkeypatch.setattr(verify_claim, "_judge_stances", _fake_judge)
    # Capture persistence instead of hitting a real DB (and prove it fires).
    recorded: list[tuple] = []
    monkeypatch.setattr(
        stance_store, "record_stances", lambda claim, verdict, evidence: recorded.append((claim, verdict, evidence)) or len(evidence)
    )
    return recorded


def _result(claim: str, *, persist: bool = False) -> dict:
    """Drive the generator handler and return verify_claim's parsed payload."""
    gen = verify_claim.run({"claim": claim, "persist": persist})
    result = None
    try:
        while True:
            next(gen)
    except StopIteration as stop:
        result = stop.value
    return json.loads(result)


def test_supported_claim_is_graded_strong(_patched: None) -> None:
    # High-confidence supporting evidence → 强支持.
    result = _result(CLAIM)
    assert result["支持等级"] == "强支持"
    assert result["判定版本"] == stance_judge.JUDGE_VERSION
    assert result["证据"][0]["证据句"] == "A cohort study associating coffee intake with lower CVD risk."
    assert result["证据"][0]["置信度"] == 0.95


def test_default_verification_does_not_persist_stance_asset(_patched: list[tuple]) -> None:
    _result(CLAIM)
    assert _patched == []


def test_negation_gets_different_verdict_from_claim(_patched: None) -> None:
    # The crack from Step 0 is closed: a claim and its negation, from the same
    # evidence, must not receive the same verdict.
    claim_verdict = _result(CLAIM)["支持等级"]
    negation = _result(NEGATION)
    assert negation["支持等级"] != claim_verdict
    assert negation["支持等级"] == "证据反驳"
    assert negation["证据立场统计"]["反驳"] == 1


def test_low_confidence_is_rejected(_patched: list[tuple], monkeypatch: pytest.MonkeyPatch) -> None:
    # Calibration: a stance the judge is unsure about must not drive a confident
    # verdict — the tool prefers 证据不足 (rejection) with a visible reason.
    monkeypatch.setattr(
        verify_claim,
        "_judge_stances",
        lambda claim, texts: stance_judge.JudgeResult(
            ok=True,
            judgements=[_judgement("SUPPORT", confidence=0.35, sentence="A cohort study associating coffee intake with lower CVD risk.")],
            note="",
        ),
    )
    result = _result(CLAIM)
    assert result["支持等级"] == "证据不足"
    assert "置信度" in (result.get("拒答原因") or "")
    assert _patched == []  # 未产生可采信立场 → 不入库


def test_qualification_mismatch_downgrades_to_insufficient(
    _patched: list[tuple], monkeypatch: pytest.MonkeyPatch
) -> None:
    # 限定条件: evidence about a different population is NOT support for the
    # general claim — it surfaces as 限定条件 and cannot drive a verdict.
    monkeypatch.setattr(
        verify_claim,
        "_judge_stances",
        lambda claim, texts: stance_judge.JudgeResult(
            ok=True,
            judgements=[
                _judgement(
                    "SUPPORT",
                    confidence=0.95,
                    sentence="A cohort study associating coffee intake with lower CVD risk.",
                    qualification="人群:小鼠模型,与论断隐含的人类对象不一致",
                )
            ],
            note="",
        ),
    )
    result = _result(CLAIM)
    assert result["支持等级"] == "证据不足"
    assert result.get("限定条件")
    assert _patched == []


def test_similarity_fallback_only_concludes_insufficient(
    _patched: list[tuple], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Fallback discipline (国赛硬约束): with no usable LLM judge, the tool must
    # not crash AND must not emit 强支持/部分支持 — similarity measures
    # relatedness, not entailment. Only 证据不足 is allowed.
    monkeypatch.setattr(verify_claim, "_judge_stances", lambda *_a, **_k: stance_judge.JudgeResult(ok=False))
    result = _result(CLAIM)
    assert result["判定方式"] == "similarity"
    assert result["支持等级"] == "证据不足"
    assert "拒答原因" in result
    assert _patched == []  # no stance labels -> nothing to persist


def test_stance_run_persists_all_judged_evidence(_patched: list[tuple]) -> None:
    # 矛盾即资产: a stance-judged run records every judged evidence row (not
    # just the displayed top 4), with claim, verdict and L3 fields attached.
    _result(CLAIM, persist=True)
    assert len(_patched) == 1
    claim, verdict, evidence = _patched[0]
    assert claim == CLAIM
    assert verdict == "强支持"
    assert [e["paper_id"] for e in evidence] == ["W1"]
    assert evidence[0]["立场"] == "SUPPORT"
    assert evidence[0]["接地相似度"] == 0.9
    assert evidence[0]["置信度"] == 0.95
    assert evidence[0]["判定版本"] == stance_judge.JUDGE_VERSION


def test_persist_failure_is_not_reported_as_written(_patched: list[tuple], monkeypatch: pytest.MonkeyPatch) -> None:
    """A failed derived-asset write must stay visible instead of being claimed."""
    from backend.app.services.stance import store as stance_store

    monkeypatch.setattr(stance_store, "record_stances", lambda *_args: 0)
    result = _result(CLAIM, persist=True)
    assert result["支持等级"] == "强支持"
    assert result["资产写入"]["状态"] == "未写入"
    assert result["资产写入"]["已确认记录数"] == 0


def test_nonverbatim_evidence_sentence_is_rejected(_patched: list[tuple], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        verify_claim,
        "_judge_stances",
        lambda claim, texts: stance_judge.JudgeResult(
            ok=True,
            judgements=[_judgement("SUPPORT", confidence=0.99, sentence="This sentence was invented.")],
        ),
    )
    result = _result(CLAIM)
    assert result["支持等级"] == "证据不足"
    assert result["证据"][0]["立场"] == "NEUTRAL"
    assert "核验" in result["证据"][0]["限定条件"]
    assert _patched == []


def test_no_retrieval_results_yields_insufficient_not_neutral_verdict(
    _patched: list[tuple], monkeypatch: pytest.MonkeyPatch
) -> None:
    # 无检索结果: 明确的「未检索到相关文献」拒答, 与「低置信拒答」和
    # 「解析失败回退」都是不同的输出路径, 不得混同。
    from backend.app.services import retrieval_service

    monkeypatch.setattr(retrieval_service, "search", lambda query, limit=6: [])
    result = _result(CLAIM)
    assert result["支持等级"] == "证据不足"
    assert "未检索到相关文献" in result["理由"]
    assert result["证据"] == []
    assert _patched == []


def test_empty_claim_is_rejected_upfront() -> None:
    gen = verify_claim.run({"claim": "   "})
    try:
        next(gen)
    except StopIteration as stop:
        message = stop.value
    assert "为空" in message


def test_conflicting_evidence_yields_dispute(
    _patched: list[tuple], monkeypatch: pytest.MonkeyPatch
) -> None:
    # 同一论断的两条证据一条支持一条反驳 → 存在争议, 不偏袒任一侧。
    from backend.app.services import retrieval_service

    monkeypatch.setattr(
        retrieval_service,
        "search",
        lambda query, limit=6: [
            SimpleNamespace(
                paper_id="W1",
                title="Coffee consumption and cardiovascular outcomes",
                snippet="A cohort study associating coffee intake with lower CVD risk.",
                year=2023,
            ),
            SimpleNamespace(
                paper_id="W2",
                title="Coffee consumption and cardiovascular outcomes",
                snippet="A cohort study associating coffee intake with higher CVD risk.",
                year=2022,
            ),
        ],
    )
    monkeypatch.setattr(
        verify_claim,
        "_judge_stances",
        lambda claim, texts: stance_judge.JudgeResult(
            ok=True,
            judgements=[
                _judgement("SUPPORT", 0.95, "A cohort study associating coffee intake with lower CVD risk."),
                _judgement("CONTRADICT", 0.9, "A cohort study associating coffee intake with higher CVD risk."),
            ],
            note="",
        ),
    )
    result = _result(CLAIM)
    assert result["支持等级"] == "存在争议"
    assert result["证据立场统计"]["支持"] == 1
    assert result["证据立场统计"]["反驳"] == 1
    assert "正反两面" in result["提示"]


def test_nonstandard_label_fallback_reports_format_reason(
    _patched: list[tuple], monkeypatch: pytest.MonkeyPatch
) -> None:
    # judge 输出非标准标签 → ok=False → 走 similarity 回退, 拒答原因须
    # 说明是「输出格式异常」而非笼统的「不可用」。
    monkeypatch.setattr(
        verify_claim,
        "_judge_stances",
        lambda *_a, **_k: stance_judge.JudgeResult(ok=False, judgements=[], note="format error: nonstandard stance label 'AGREE'"),
    )
    result = _result(CLAIM)
    assert result["判定方式"] == "similarity"
    assert result["支持等级"] == "证据不足"
    assert "格式异常" in result["拒答原因"]
    assert "AGREE" in result["拒答原因"]
    assert _patched == []


def test_missing_confidence_cannot_drive_verdict(
    _patched: list[tuple], monkeypatch: pytest.MonkeyPatch
) -> None:
    # confidence 缺失时 judge 以 0.0 记置信 (低于阈值 0.5), 绝不默认 0.5:
    # 该证据只能进入低置信拒答, 不得意外导出 部分支持/证据反驳。
    monkeypatch.setattr(
        verify_claim,
        "_judge_stances",
        lambda claim, texts: stance_judge.JudgeResult(
            ok=True,
            judgements=[_judgement("SUPPORT", confidence=0.0, sentence="A cohort study associating coffee intake with lower CVD risk.")],
            note="",
        ),
    )
    result = _result(CLAIM)
    assert result["支持等级"] == "证据不足"
    assert "置信度" in (result.get("拒答原因") or "")
    assert _patched == []


@pytest.mark.parametrize("bad_conf", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_confidence_cannot_drive_verdict_or_persist(
    _patched: list[tuple], monkeypatch: pytest.MonkeyPatch, bad_conf: float
) -> None:
    # 防御层: 即便 mock judge 漏检而返回 NaN/±Infinity 置信度, verify_claim 的
    # 聚合 (confidence >= 阈值) 对非有限值恒为 False — 不得导出支持/反驳,
    # 也不得写入争议资产。
    monkeypatch.setattr(
        verify_claim,
        "_judge_stances",
        lambda claim, texts: stance_judge.JudgeResult(
            ok=True,
            judgements=[_judgement("SUPPORT", confidence=bad_conf, sentence="A cohort study associating coffee intake with lower CVD risk.")],
            note="",
        ),
    )
    result = _result(CLAIM, persist=True)
    assert result["支持等级"] == "证据不足"
    assert _patched == []  # 非有限置信度不得写入 claim_evidence_stance
