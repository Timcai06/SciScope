"""L3 judge fail-closed contract: 格式异常/模型失败绝不静默降成 NEUTRAL.

硬约束: 不把格式异常或模型失败静默降成 NEUTRAL。judge 返回 ``ok=False``
时, 调用方 (verify_claim) 必须走 similarity 回退并只报「证据不足」。
"""

from __future__ import annotations

import json

import pytest

from backend.app.services.stance import judge as stance_judge

EVIDENCE = ["Coffee intake is associated with lower CVD risk in a cohort study."]


def _mock_llm(raw: str) -> None:
    from backend.app.services import deepseek_provider

    class _Fake:
        def complete(self, prompt: str) -> str:
            return raw

    deepseek_provider.get_llm_provider = lambda: _Fake()  # type: ignore[assignment]


def _judge(raw: str) -> stance_judge.JudgeResult:
    from backend.app.services.stance import judge as judge_module

    _mock_llm(raw)
    return judge_module.judge_evidence("咖啡能降低心脏病风险", EVIDENCE)


def test_wellformed_output_ok() -> None:
    result = _judge(
        json.dumps([{"stance": "SUPPORT", "confidence": 0.9, "sentence": "Coffee intake is associated with lower CVD risk in a cohort study.", "qualification": None}])
    )
    assert result.ok
    assert len(result.judgements) == 1
    assert result.judgements[0].stance == "SUPPORT"


def test_unknown_stance_label_fails_closed() -> None:
    # 非标准标签 (如 "AGREE") 不得静默降成 NEUTRAL 并返回 ok=True。
    result = _judge(
        json.dumps([{"stance": "AGREE", "confidence": 0.9, "sentence": "Coffee intake is associated with lower CVD risk in a cohort study.", "qualification": None}])
    )
    assert not result.ok
    assert "format error" in result.note
    assert "AGREE" in result.note
    assert result.judgements == []


def test_empty_reply_array_fails_closed() -> None:
    # 空数组 []: 数量不足, 不得用默认 NEUTRAL 填充后 ok=True。
    result = _judge("[]")
    assert not result.ok
    assert "length" in result.note
    assert result.judgements == []


def test_surplus_elements_fail_closed() -> None:
    # 多余元素: 数量超过证据数, 不得静默截断。
    result = _judge(
        json.dumps([
            {"stance": "SUPPORT", "confidence": 0.9, "sentence": "Coffee intake is associated with lower CVD risk in a cohort study.", "qualification": None},
            {"stance": "NEUTRAL", "confidence": 0.5, "sentence": "", "qualification": None},
        ])
    )
    assert not result.ok
    assert "length" in result.note
    assert result.judgements == []


def test_missing_stance_field_fails_closed() -> None:
    result = _judge(
        json.dumps([{"confidence": 0.9, "sentence": "Coffee intake is associated with lower CVD risk in a cohort study."}])
    )
    assert not result.ok
    assert "missing stance" in result.note


def test_non_object_element_fails_closed() -> None:
    result = _judge('["SUPPORT"]')
    assert not result.ok
    assert "non-object" in result.note


def test_missing_confidence_is_zero_not_half() -> None:
    # confidence 缺失/不可解析 → 0.0 (低于聚合阈值 0.5), 绝不默认 0.5,
    # 否则可能意外导出 部分支持/证据反驳。
    from backend.app.services.stance import judge as judge_module

    _mock_llm(
        json.dumps([{"stance": "SUPPORT", "sentence": "Coffee intake is associated with lower CVD risk in a cohort study."}])
    )
    result = judge_module.judge_evidence("咖啡能降低心脏病风险", EVIDENCE)
    assert result.ok
    assert result.judgements[0].confidence == 0.0


@pytest.mark.parametrize("raw_conf", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_confidence_fails_closed(raw_conf: str) -> None:
    # NaN/Infinity: json.loads 接受这些非标准值, 钳制会把 NaN/Infinity 变成
    # 1.0 从而可导出「强支持」。非有限置信度必须 fail-closed, 走证据不足回退。
    result = _judge(
        json.dumps([
            {"stance": "SUPPORT", "confidence": json.loads(raw_conf), "sentence": "Coffee intake is associated with lower CVD risk in a cohort study."}
        ])
    )
    assert not result.ok
    assert "non-finite" in result.note
    assert result.judgements == []


def test_garbage_non_json_reply_fails_closed() -> None:
    result = _judge("I think this supports the claim, definitely!")
    assert not result.ok
    assert result.judgements == []


def test_empty_evidence_fails_closed() -> None:
    from backend.app.services.stance import judge as judge_module

    result = judge_module.judge_evidence("claim", [])
    assert not result.ok
    assert result.note == "no evidence"


def test_coerce_rejects_any_nonstandard_member() -> None:
    raw = [
        {"stance": "AGREE", "confidence": 0.9},
        {"stance": "NO", "confidence": 0.8},
        {"stance": "SUPPORT", "confidence": 0.95},
    ]
    judgements, reason = stance_judge._coerce_judgements(raw, 3)
    assert judgements == []
    assert reason is not None and "AGREE" in reason


def test_coerce_length_mismatch_rejected() -> None:
    judgements, reason = stance_judge._coerce_judgements([{"stance": "SUPPORT", "confidence": 0.9}], 2)
    assert judgements == []
    assert "length" in (reason or "")


def test_genuine_neutral_is_not_rejected() -> None:
    raw = [{"stance": "NEUTRAL", "confidence": 0.5, "sentence": "", "qualification": None}]
    judgements, reason = stance_judge._coerce_judgements(raw, 1)
    assert reason is None
    assert judgements[0].stance == "NEUTRAL"
