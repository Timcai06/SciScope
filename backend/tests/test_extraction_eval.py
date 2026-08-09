"""D04 抽取质量评测聚合测试（修订版）。

覆盖：
- record_sha256 唯一匹配；缺 sha / 版本不匹配 → fail-closed unrateable；
- 同 (source, paper_id) 多版本歧义拒绝（不任选一条）；
- 正确率只来自人工裁决（阶段 B），无裁决时 pending、不自动判正确；
- gold_locatable 真正参与（locatable_mismatch）；
- Wilson CI、空 gold 安全、端到端（含 adjudications）。
"""

import json

from src.infra.extraction_eval import (
    SCHEMA_VERSION,
    evaluate_extraction,
    run_extraction_eval,
    wilson_ci,
)


def _structured_record(**overrides):
    record = {
        "schema_version": "structured-extraction/v1",
        "source": "s1",
        "paper_id": "P1",
        "record_sha256": "sha-1",
        "fields": [
            {
                "field": "study_population",
                "status": "extracted",
                "value": "we studied 50 patients",
                "confidence": 0.8,
                "evidence": {
                    "chunk_uid": "c1",
                    "locator": {"base": "field_text"},
                    "sentence": "we studied 50 patients",
                    "span": {"start_char": 0, "end_char": 24},
                },
            },
            {"field": "main_result", "status": "extracted", "value": "Results show 92%", "confidence": 0.6,
             "evidence": {"chunk_uid": "c2", "locator": {"base": "normalized_text"},
                          "sentence": "Results show 92%", "span": {"start_char": 0, "end_char": 17}}},
            {"field": "limitations", "status": "not_found", "value": "", "confidence": 0.0},
        ],
    }
    record.update(overrides)
    return record


def _gold(field="main_result", *, sha="sha-1", present=True, value="92%", locatable=True, source="s1", paper="P1"):
    return {
        "source": source,
        "paper_id": paper,
        "record_sha256": sha,
        "field": field,
        "gold_present": present,
        "gold_value": value,
        "gold_locatable": locatable,
    }


def _adjudication(field, judgment="correct", *, sha="sha-1", source="s1", paper="P1"):
    return {"source": source, "paper_id": paper, "record_sha256": sha, "field": field, "judgment": judgment}


# --- Wilson CI ---------------------------------------------------------------


def test_wilson_ci_known_value():
    low, high = wilson_ci(50, 100)
    assert 0.39 < low < 0.42
    assert 0.58 < high < 0.61
    assert wilson_ci(0, 0) is None


# --- record_sha256 唯一匹配与 fail-closed ------------------------------------


def test_gold_must_match_record_sha256():
    report = evaluate_extraction(
        structured_records=[_structured_record()],
        gold_records=[
            _gold(sha="sha-1"),  # 匹配
            _gold(sha="sha-wrong"),  # 版本不匹配
            _gold(field="limitations", sha=""),  # 缺 sha
        ],
        adjudications=[_adjudication("main_result")],
    )

    main = next(f for f in report.fields if f.field == "main_result")
    assert main.n == 1
    assert main.correct == 1

    assert len(report.unrateable) == 2
    reasons = {u["reason"] for u in report.unrateable}
    assert any(r.startswith("record_sha256_no_match") for r in reasons)
    assert "missing_record_sha256" in reasons


def test_ambiguous_multiple_versions_fail_closed():
    # 同 (source, paper_id) 两个版本；gold 缺 sha → 不得任选一条。
    report = evaluate_extraction(
        structured_records=[
            _structured_record(record_sha256="sha-v1"),
            _structured_record(record_sha256="sha-v2"),
        ],
        gold_records=[_gold(sha="")],
    )

    assert len(report.unrateable) == 1
    assert report.unrateable[0]["reason"] == "missing_record_sha256"
    assert next(f for f in report.fields if f.field == "main_result").n == 0


def test_gold_with_explicit_sha_disambiguates():
    report = evaluate_extraction(
        structured_records=[
            _structured_record(record_sha256="sha-v1"),
            _structured_record(record_sha256="sha-v2"),
        ],
        gold_records=[_gold(sha="sha-v2")],
        adjudications=[_adjudication("main_result", sha="sha-v2")],
    )

    assert report.unrateable == []
    main = next(f for f in report.fields if f.field == "main_result")
    assert main.n == 1
    assert main.correct == 1


# --- 人工裁决统计（阶段 B） --------------------------------------------------


def test_correctness_only_from_human_adjudication():
    structured = [_structured_record()]
    gold = [
        _gold(field="main_result", value="92%"),
        _gold(field="study_population", value="patients"),
        _gold(field="limitations"),
    ]
    adjudications = [
        _adjudication("main_result", "correct"),
        _adjudication("study_population", "incorrect"),
        _adjudication("limitations", "unsure"),
    ]

    report = evaluate_extraction(structured, gold, adjudications)

    by_field = {f.field: f for f in report.fields}
    assert by_field["main_result"].correct == 1
    assert by_field["study_population"].correct == 0
    assert any(f["reason"] == "human_judged_incorrect" for f in by_field["study_population"].failures)
    assert by_field["limitations"].correct == 0
    assert by_field["limitations"].pending_human_adjudication is False


def test_without_adjudication_correct_is_pending_not_auto():
    # 程序不得用模糊字符串匹配替代人工裁决：无裁决 → correct=0 + pending。
    report = evaluate_extraction(
        structured_records=[_structured_record()],
        gold_records=[_gold(field="main_result", value="92%")],
    )

    main = next(f for f in report.fields if f.field == "main_result")
    assert main.correct == 0
    assert main.correctness == 0.0
    assert main.pending_human_adjudication is True


# --- gold_locatable 参与 ------------------------------------------------------


def test_locatable_mismatch_when_human_says_locatable_but_span_invalid():
    broken = _structured_record()
    broken["fields"][1]["evidence"] = None  # main_result 无 span
    report = evaluate_extraction(
        structured_records=[broken],
        gold_records=[
            _gold(field="study_population", locatable=True),
            _gold(field="main_result", locatable=True),
        ],
        adjudications=[
            _adjudication("study_population", "correct"),
            _adjudication("main_result", "correct"),
        ],
    )

    by_field = {f.field: f for f in report.fields}
    population = by_field["study_population"]
    assert population.locatable == 1
    assert population.gold_locatable_true == 1
    assert population.locatable_mismatch == 0

    result = by_field["main_result"]
    assert result.extracted == 1
    assert result.locatable == 0  # 程序无法定位
    assert result.gold_locatable_true == 1
    assert result.locatable_mismatch == 1
    assert any(f["reason"].startswith("locatable_mismatch") for f in result.failures)


# --- 硬规则：gold_present=false 且系统抽取 → false positive -------------------


def test_false_positive_when_gold_absent_but_extracted():
    # 阶段 A 判定字段本不存在，但系统抽取了 → 必为 false positive；
    # 即使阶段 B 误填 correct 也不计入正确率（须先回阶段 A 更正 gold）。
    report = evaluate_extraction(
        structured_records=[_structured_record()],
        gold_records=[
            _gold(field="main_result", present=False, value=None),
        ],
        adjudications=[_adjudication("main_result", "correct")],
    )

    main = next(f for f in report.fields if f.field == "main_result")
    assert main.correct == 0
    assert main.correctness == 0.0
    assert main.pending_count == 0
    assert any(f["reason"] == "false_positive:gold_absent_but_extracted" for f in main.failures)


def test_unadjudicated_false_positive_remains_pending():
    # 假阳性是指标硬失败，但没有阶段 B 裁决时，不能冒充为“已裁决的错误”
    # 并进入正确率分母。
    report = evaluate_extraction(
        structured_records=[_structured_record()],
        gold_records=[_gold(field="main_result", present=False, value=None)],
        adjudications=[],
    )

    main = next(f for f in report.fields if f.field == "main_result")
    assert main.correct == 0
    assert main.pending_count == 1
    assert main.pending_human_adjudication is True
    assert main.correctness == 0.0
    assert main.ci_low is None and main.ci_high is None
    assert any(f["reason"] == "false_positive:gold_absent_but_extracted" for f in main.failures)


def test_true_negative_when_gold_absent_and_not_extracted():
    # gold_present=false 且系统未抽取 → 裁决 correct 正常计入（阴性正确）。
    report = evaluate_extraction(
        structured_records=[_structured_record()],
        gold_records=[
            _gold(field="conclusion", present=False, value=None),
        ],
        adjudications=[_adjudication("conclusion", "correct")],
    )

    conclusion = next(f for f in report.fields if f.field == "conclusion")
    assert conclusion.extracted == 0  # 系统未抽取该字段
    assert conclusion.correct == 1
    assert not any(f["reason"].startswith("false_positive") for f in conclusion.failures)


def test_pending_samples_excluded_from_correctness_denominator():
    # 同一字段的 2 个可评测样本，只有 1 个裁决 → pending_count=1；
    # 正确率分母=该字段已裁决数，pending 未裁决样本不当作错误。
    second_record = _structured_record(paper_id="P2", record_sha256="sha-2")
    report = evaluate_extraction(
        structured_records=[_structured_record(), second_record],
        gold_records=[
            _gold(field="main_result"),
            _gold(field="main_result", paper="P2", sha="sha-2"),
        ],
        adjudications=[_adjudication("main_result", "correct")],
    )

    main = next(f for f in report.fields if f.field == "main_result")
    assert main.n == 2
    assert main.correct == 1
    assert main.pending_count == 1
    assert main.pending_human_adjudication is True
    assert main.correctness == 1.0  # 1/1 已裁决
    assert main.ci_low is not None and main.ci_high is not None


def test_all_pending_yields_no_correctness_data():
    report = evaluate_extraction(
        structured_records=[_structured_record()],
        gold_records=[_gold(field="main_result")],
        adjudications=[],
    )

    main = next(f for f in report.fields if f.field == "main_result")
    assert main.pending_count == 1
    assert main.correctness == 0.0
    assert main.ci_low is None and main.ci_high is None  # 无已裁决样本 → 无 CI


# --- 空 gold / 端到端 --------------------------------------------------------


def test_empty_gold_is_safe():
    report = evaluate_extraction(structured_records=[_structured_record()], gold_records=[])
    assert report.gold_entries == 0
    assert report.unrateable == []
    for f in report.fields:
        assert f.n == 0
        assert f.ci_low is None and f.ci_high is None


def test_run_extraction_eval_end_to_end(tmp_path):
    structured_path = tmp_path / "structured.jsonl"
    structured_path.write_text(json.dumps(_structured_record(), ensure_ascii=False) + "\n", encoding="utf-8")
    gold_path = tmp_path / "gold.jsonl"
    gold_path.write_text(
        "\n".join(
            [
                json.dumps(_gold(field="main_result", value="92%"), ensure_ascii=False),
                json.dumps(_gold(field="study_population", value="patients"), ensure_ascii=False),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    ad_path = tmp_path / "adjudications.jsonl"
    ad_path.write_text(
        json.dumps(_adjudication("main_result", "correct"), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    summary = run_extraction_eval(
        input_structured_path=structured_path,
        gold_path=gold_path,
        adjudication_path=ad_path,
        output_dir=tmp_path / "out",
    )

    assert summary["schema_version"] == SCHEMA_VERSION
    assert summary["gold_entries"] == 2
    assert summary["adjudications"] == 1
    report = json.loads((tmp_path / "out" / "eval_report.json").read_text(encoding="utf-8"))
    assert report["schema_version"] == SCHEMA_VERSION
    main = next(f for f in report["fields"] if f["field"] == "main_result")
    assert main["correct"] == 1
    assert main["pending_human_adjudication"] is False
    population = next(f for f in report["fields"] if f["field"] == "study_population")
    assert population["pending_human_adjudication"] is True
