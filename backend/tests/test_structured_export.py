"""D05 结构化文献出口契约测试。

覆盖：
- 按 paper ID 返回带 provenance 的结构化字段 + 许可边界；
- 「未抽取」与「未授权展示」的区别；
- 无来源字段不作为确定事实输出；
- Agent tool 契约（注册、只读、索引未就绪不伪装）；
- 可复现调用记录（测试内一次真实查询）。
"""

import json

from src.infra.structured_export import (
    SCHEMA_VERSION,
    load_admission_index,
    load_structured_index,
    query_structured,
)


def _structured_record(source="s1", paper_id="PX-001", *, with_fields=True):
    fields = [
        {
            "field": "study_population",
            "status": "extracted",
            "value": "we studied 50 patients with cancer",
            "confidence": 0.8,
            "evidence": {
                "chunk_uid": "c1",
                "locator": {"base": "field_text"},
                "sentence": "we studied 50 patients with cancer",
                "span": {"start_char": 0, "end_char": 36},
            },
        },
        {
            "field": "main_result",
            "status": "extracted",
            "value": "Results show 92% accuracy",
            "confidence": 0.6,
            "evidence": {
                "chunk_uid": "c2",
                "locator": {"base": "normalized_text"},
                "sentence": "Results show 92% accuracy",
                "span": {"start_char": 12, "end_char": 36},
            },
        },
        {"field": "limitations", "status": "not_found", "value": "", "confidence": 0.0},
        {
            "field": "conclusion",
            "status": "low_confidence",
            "value": "",
            "confidence": 0.4,
            "candidates": ["we suggest wider validation"],
            "reason": "indicator_not_found_using_abstract_fallback",
        },
    ]
    record = {
        "schema_version": "structured-extraction/v1",
        "source": source,
        "paper_id": paper_id,
        "record_sha256": "r" * 64,
        "fields": fields if with_fields else [],
    }
    return record


def _admission_record(source="s1", paper_id="PX-001", *, usage_rights="snippet", license="cc-by"):
    return {
        "paper_id": paper_id,
        "source": source,
        "license": license,
        "usage_rights": usage_rights,
        "source_file_sha256": "f" * 64,
    }


def _indexes(tmp_path, structured, admission):
    structured_path = tmp_path / "structured.jsonl"
    structured_path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in structured) + "\n", encoding="utf-8"
    )
    admission_path = tmp_path / "staged.jsonl"
    admission_path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in admission) + "\n", encoding="utf-8"
    )
    return (
        load_structured_index(structured_path),
        load_admission_index(admission_path),
    )


# --- 数据层契约 -------------------------------------------------------------


def test_query_returns_fields_with_provenance_and_license(tmp_path):
    structured_idx, admission_idx = _indexes(
        tmp_path,
        [_structured_record()],
        [_admission_record()],
    )

    view = query_structured(
        "PX-001", "s1", structured_index=structured_idx, admission_index=admission_idx
    )

    assert view["schema_version"] == SCHEMA_VERSION
    assert view["paper_id"] == "PX-001"
    assert view["source"] == "s1"
    assert view["record_sha256"] == "r" * 64
    assert view["license"] == "cc-by"
    assert view["usage_rights"] == "snippet"
    assert view["display_policy"] == {"authorized": True, "reason": "usage_rights_allows_display"}

    extracted = {f["field"]: f for f in view["fields"] if f["status"] == "extracted"}
    assert extracted["study_population"]["value"] == "we studied 50 patients with cancer"
    assert extracted["study_population"]["confidence"] == 0.8
    # 已授权（snippet）：完整 provenance 保留（证据句 + span）。
    assert extracted["study_population"]["evidence"]["chunk_uid"] == "c1"
    assert extracted["study_population"]["evidence"]["sentence"] == "we studied 50 patients with cancer"
    assert extracted["study_population"]["evidence"]["span"]["start_char"] >= 0


def test_not_extracted_fields_do_not_output_value(tmp_path):
    structured_idx, admission_idx = _indexes(
        tmp_path,
        [_structured_record()],
        [_admission_record()],
    )

    view = query_structured("PX-001", "s1", structured_index=structured_idx, admission_index=admission_idx)

    by_field = {f["field"]: f for f in view["fields"]}
    limitations = by_field["limitations"]
    assert limitations["status"] == "not_found"
    assert limitations["value"] is None  # 未抽取不作为确定事实
    conclusion = by_field["conclusion"]
    assert conclusion["status"] == "low_confidence"
    assert conclusion["value"] is None
    assert conclusion["pending_candidates"]  # 待审候选句


def test_authorized_extracted_field_without_evidence_is_not_factual(tmp_path):
    # 即使许可允许展示，status=extracted 但没有完整可回链 evidence 时也不能输出 value。
    record = _structured_record()
    main_result = next(field for field in record["fields"] if field["field"] == "main_result")
    main_result["value"] = "unguarded fact"
    main_result["evidence"] = None
    structured_idx, admission_idx = _indexes(
        tmp_path,
        [record],
        [_admission_record(usage_rights="snippet", license="cc-by")],
    )

    view = query_structured("PX-001", "s1", structured_index=structured_idx, admission_index=admission_idx)
    main_view = next(field for field in view["fields"] if field["field"] == "main_result")

    assert view["display_policy"]["authorized"] is True
    assert main_view["value"] is None
    assert main_view["display"] == "not_grounded"
    assert main_view["reason"] == "extracted_field_missing_valid_evidence"
    assert "evidence" not in main_view
    assert "unguarded fact" not in json.dumps(view, ensure_ascii=False)


def test_indexable_blocks_value_display(tmp_path):
    # 许可分级 indexable → 只可索引元数据，正文片段级字段不授权展示。
    structured_idx, admission_idx = _indexes(
        tmp_path,
        [_structured_record()],
        [_admission_record(usage_rights="indexable", license="cc-by")],
    )

    view = query_structured("PX-001", "s1", structured_index=structured_idx, admission_index=admission_idx)

    assert view["display_policy"]["authorized"] is False
    assert view["display_policy"]["reason"] == "indexable_only_metadata_not_display"
    extracted = {f["field"]: f for f in view["fields"] if f["status"] == "extracted"}
    assert extracted["study_population"]["value"] is None
    assert extracted["study_population"]["display"] == "not_authorized_display"
    # 最小审计引用（不泄露正文证据句 / span / 精确 offset）。
    assert "evidence" not in extracted["study_population"]
    assert extracted["study_population"]["audit"]["chunk_uid"] == "c1"
    assert extracted["study_population"]["audit"]["locator_type"] == "field_text"
    assert extracted["study_population"]["audit"]["confidence"] == 0.8
    # 正文证据句不得出现在任何序列化输出中（验收：json.dumps 不包含测试正文句）。
    assert "we studied 50 patients with cancer" not in json.dumps(view, ensure_ascii=False)
    assert "Results show 92% accuracy" not in json.dumps(view, ensure_ascii=False)


def test_unknown_usage_rights_is_conservative(tmp_path):
    structured_idx, admission_idx = _indexes(
        tmp_path,
        [_structured_record()],
        [_admission_record(usage_rights="", license="unknown")],
    )

    view = query_structured("PX-001", "s1", structured_index=structured_idx, admission_index=admission_idx)

    assert view["usage_rights"] == "unknown"
    assert view["display_policy"] == {"authorized": False, "reason": "usage_rights_unknown_conservative"}
    # 未授权：value、evidence.sentence、pending_candidates 一律不返回。
    assert next(f for f in view["fields"] if f["field"] == "main_result")["value"] is None
    assert all("evidence" not in f for f in view["fields"])
    assert all("pending_candidates" not in f for f in view["fields"])
    assert "we studied 50 patients with cancer" not in json.dumps(view, ensure_ascii=False)
    assert "Results show 92% accuracy" not in json.dumps(view, ensure_ascii=False)
    # 低置信字段的候选句（原文）同样不泄露。
    assert "we suggest wider validation" not in json.dumps(view, ensure_ascii=False)


def test_missing_paper_returns_not_found(tmp_path):
    structured_idx, admission_idx = _indexes(
        tmp_path,
        [_structured_record()],
        [_admission_record()],
    )

    view = query_structured("PX-NOPE", "s1", structured_index=structured_idx, admission_index=admission_idx)

    assert view["status"] == "not_found"
    assert view["reason"] == "no_structured_record"


def test_multiple_sources_return_matches(tmp_path):
    structured_idx, admission_idx = _indexes(
        tmp_path,
        [_structured_record(source="s1", paper_id="P1"), _structured_record(source="s2", paper_id="P1")],
        [_admission_record(source="s1", paper_id="P1"), _admission_record(source="s2", paper_id="P1")],
    )

    view = query_structured("P1", structured_index=structured_idx, admission_index=admission_idx)

    assert view["status"] == "multiple_sources"
    assert {m["source"] for m in view["matches"]} == {"s1", "s2"}
    for match in view["matches"]:
        assert match["display_policy"]["authorized"] is True


# --- Agent tool 契约 ---------------------------------------------------------


def test_tool_is_registered_and_read_only():
    from backend.app.agent.tools import NATIVE_TOOLS

    tool = next((t for t in NATIVE_TOOLS if t.name == "paper_structured"), None)
    assert tool is not None, "paper_structured 应已注册到 NATIVE_TOOLS"
    assert tool.side_effect == "read"


def test_tool_run_returns_queryable_view(tmp_path, monkeypatch):
    from backend.app.agent.tools.paper_structured import run

    structured_path = tmp_path / "structured.jsonl"
    structured_path.write_text(
        json.dumps(_structured_record(), ensure_ascii=False) + "\n", encoding="utf-8"
    )
    admission_path = tmp_path / "staged.jsonl"
    admission_path.write_text(
        json.dumps(_admission_record(), ensure_ascii=False) + "\n", encoding="utf-8"
    )
    monkeypatch.setenv("SCISCOPE_STRUCTURED_PATH", str(structured_path))
    monkeypatch.setenv("SCISCOPE_ADMISSION_PATH", str(admission_path))

    payload = json.loads(run({"paper_id": "PX-001", "source": "s1"}))

    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["paper_id"] == "PX-001"
    assert any(f["field"] == "study_population" and f["status"] == "extracted" for f in payload["fields"])


def test_tool_run_reports_index_unavailable(tmp_path, monkeypatch):
    from backend.app.agent.tools.paper_structured import run

    monkeypatch.setenv("SCISCOPE_STRUCTURED_PATH", str(tmp_path / "missing" / "structured.jsonl"))
    monkeypatch.setenv("SCISCOPE_ADMISSION_PATH", str(tmp_path / "missing" / "staged.jsonl"))

    message = run({"paper_id": "PX-001"})

    assert "未就绪" in message  # 不伪装成功


def test_tool_run_does_not_leak_body_for_indexable(tmp_path, monkeypatch):
    # Agent tool 输出同样不泄露：indexable 许可下正文证据句不得出现在返回中。
    from backend.app.agent.tools.paper_structured import run

    structured_path = tmp_path / "structured.jsonl"
    structured_path.write_text(
        json.dumps(_structured_record(), ensure_ascii=False) + "\n", encoding="utf-8"
    )
    admission_path = tmp_path / "staged.jsonl"
    admission_path.write_text(
        json.dumps(_admission_record(usage_rights="indexable", license="cc-by"), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("SCISCOPE_STRUCTURED_PATH", str(structured_path))
    monkeypatch.setenv("SCISCOPE_ADMISSION_PATH", str(admission_path))

    payload = run({"paper_id": "PX-001", "source": "s1"})

    assert "we studied 50 patients with cancer" not in payload
    assert "Results show 92% accuracy" not in payload
    assert "we suggest wider validation" not in payload
    parsed = json.loads(payload)
    assert parsed["display_policy"]["authorized"] is False
    extracted = {f["field"]: f for f in parsed["fields"] if f["status"] == "extracted"}
    assert "audit" in extracted["study_population"]
    assert "evidence" not in extracted["study_population"]


def test_indexable_does_not_leak_numeric_sentence(tmp_path):
    # numeric_findings 的 value 是含原文句的列表：indexable 下不得泄露任何句子。
    record = _structured_record()
    record["fields"].append(
        {
            "field": "numeric_findings",
            "status": "extracted",
            "value": [
                {"sentence": "Results show AUC 0.85 and 85% accuracy",
                 "span": {"start_char": 12, "end_char": 46},
                 "chunk_uid": "c9", "locator": {"base": "normalized_text"},
                 "values": [{"number": "0.85"}, {"number": "85", "unit": "%"}]}
            ],
            "confidence": 0.7,
            "evidence": {"chunk_uid": "c9", "locator": {"base": "normalized_text"},
                         "sentence": "Results show AUC 0.85 and 85% accuracy",
                         "span": {"start_char": 12, "end_char": 46}},
        }
    )
    structured_idx, admission_idx = _indexes(
        tmp_path,
        [record],
        [_admission_record(usage_rights="indexable", license="cc-by")],
    )

    view = query_structured("PX-001", "s1", structured_index=structured_idx, admission_index=admission_idx)

    assert "AUC 0.85" not in json.dumps(view, ensure_ascii=False)
    numeric = next(f for f in view["fields"] if f["field"] == "numeric_findings")
    assert numeric["status"] == "extracted"
    assert numeric["value"] is None
    assert numeric["audit"]["chunk_uid"] == "c9"


def test_multiple_sources_indexable_do_not_leak(tmp_path):
    # 多来源 matches：每个来源在 indexable 下都不得泄露正文。
    structured = [
        _structured_record(source="s1", paper_id="P1"),
        _structured_record(source="s2", paper_id="P1"),
    ]
    admission = [
        _admission_record(source="s1", paper_id="P1", usage_rights="indexable"),
        _admission_record(source="s2", paper_id="P1", usage_rights="unknown"),
    ]
    structured_idx, admission_idx = _indexes(tmp_path, structured, admission)

    view = query_structured("P1", structured_index=structured_idx, admission_index=admission_idx)

    assert view["status"] == "multiple_sources"
    assert "we studied 50 patients with cancer" not in json.dumps(view, ensure_ascii=False)
    for match in view["matches"]:
        assert match["display_policy"]["authorized"] is False
        assert "evidence" not in json.dumps(match["fields"])
