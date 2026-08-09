"""D03 关键科学信息结构化抽取测试。

覆盖验收：
- schema 有明确版本；
- 每个非空字段带 provenance（chunk_uid / locator / sentence / span）；
- 正常、缺字段、低置信/无法定位、数值单位、span 篡改等场景；
- D02 小样例端到端跑通。
"""

import json

from src.infra.chunks import stable_uid
from src.infra.structured_extraction import (
    SCHEMA_VERSION,
    _locate_sentence,
    _result_to_dict,
    _split_sentences,
    extract_from_chunks,
    run_structured_extraction,
)
from src.infra.traceable_chunks import build_traceable_chunks


def _chunks_for(**record_overrides):
    """构造一条 D02 可追溯 chunk（含全部六类字段指示词）。"""
    record = {
        "paper_id": "PX-100",
        "source": "iflytek",
        "license": "cc0",
        "language": "zh",
        "year": 2024,
        "usage_rights": "indexable",
        "source_file_sha256": "d" * 64,
        "record_sha256": "e" * 64,
        "title": "A randomized controlled trial of neural networks for cancer detection",
        "abstract": (
            "In this randomized controlled trial, we studied 120 patients with cancer. "
            "We used a neural network model. Results show AUC of 0.85 and 85% accuracy. "
            "However, a limitation is that we did not consider rare subtypes. "
            "In conclusion, our findings suggest the model improves detection."
        ),
        "full_text": (
            "第一章 我们招募了 120 patients 并随机分组。"
            "第二章 采用 neural network model 进行实验。"
            "Results show the model achieves AUC 0.85. 第三章 结论：综上所述，模型显著提升检测准确率。"
        ),
    }
    # record_sha256 必须与内容一致，否则 D02 层拒绝切片。
    from src.data_contracts.admission import compute_record_hash

    record["record_sha256"] = compute_record_hash(record)
    record.update(record_overrides)
    if "record_sha256" not in record_overrides:
        record["record_sha256"] = compute_record_hash(record)
    result = build_traceable_chunks(record)
    # 允许「无全文」类失败；但必须产出可追溯 chunk（title_abstract 或 full_text）。
    assert result.chunks, result.failures
    assert not any(f["status"] in {"missing_core_fields", "record_hash_mismatch"} for f in result.failures)
    return result.chunks


def _field(result, name):
    return next(f for f in result.fields if f.field == name)


# --- schema 版本 ------------------------------------------------------------


def test_schema_version_is_explicit():
    chunks = _chunks_for()
    result = extract_from_chunks(chunks)
    assert result.schema_version == SCHEMA_VERSION
    assert SCHEMA_VERSION == "structured-extraction/v1"


# --- 正常：全部字段提取 + provenance ----------------------------------------


def test_all_fields_extracted_with_provenance():
    chunks = _chunks_for()
    result = extract_from_chunks(chunks)

    assert result.paper_id == "PX-100"
    assert {f.field for f in result.fields} == {
        "study_population", "study_design", "main_result",
        "numeric_findings", "limitations", "conclusion",
    }

    for f in result.fields:
        if f.status == "extracted":
            assert f.evidence is not None, f"{f.field} 缺少证据"
            assert f.evidence.chunk_uid
            assert f.evidence.locator
            assert f.evidence.sentence
            assert f.evidence.span["start_char"] >= 0
            assert f.evidence.span["end_char"] > f.evidence.span["start_char"]
            # 证据句必须真实存在于来源 chunk 文本中。
            chunk = next(c for c in chunks if c["chunk_uid"] == f.evidence.chunk_uid)
            assert f.evidence.sentence in chunk["text"]
            assert 0 < f.confidence <= 1.0


def test_population_design_result_limitation_conclusion_values():
    chunks = _chunks_for()
    result = extract_from_chunks(chunks)

    assert "patients" in _field(result, "study_population").value.lower()
    assert "randomized" in _field(result, "study_design").value.lower()
    assert "results show" in _field(result, "main_result").value.lower()
    assert "limitation" in _field(result, "limitations").value.lower()
    assert "conclusion" in _field(result, "conclusion").value.lower()


def test_numeric_findings_capture_number_and_unit():
    chunks = _chunks_for()
    result = extract_from_chunks(chunks)

    numeric = _field(result, "numeric_findings")
    assert numeric.status == "extracted"
    assert numeric.value, "应有数值发现"
    all_values = [
        item
        for finding in numeric.value
        for item in finding["values"]
    ]
    assert any(item["number"] == "0.85" for item in all_values)
    assert any(item["number"] == "85" and item["unit"] == "%" for item in all_values)
    # 每个数值发现都有句子与 span 定位。
    for finding in numeric.value:
        assert finding["sentence"]
        assert finding["span"]["start_char"] >= 0


# --- 缺字段：不编造 ---------------------------------------------------------


def test_missing_indicators_yield_not_found_without_fabrication():
    chunks = _chunks_for(
        title="A general paper about science.",
        abstract="This paper describes general background information without specific findings.",
        full_text="",
    )

    result = extract_from_chunks(chunks)

    # 无指示词 → not_found，value 为空（绝不编造）。
    for name in ("study_population", "study_design", "main_result", "limitations"):
        f = _field(result, name)
        assert f.status == "not_found", f"{name} 应 not_found，实际 {f.status}"
        assert f.value == ""


def test_empty_chunks_are_safe():
    result = extract_from_chunks([])
    assert result.paper_id == ""
    for f in result.fields:
        assert f.status in ("not_found",)
        assert not f.value


# --- 低置信 / 无法定位 -------------------------------------------------------


def test_conclusion_fallback_is_low_confidence_without_value():
    chunks = _chunks_for(
        abstract="We studied patients and report the analysis. The end of the abstract.",
        full_text="",
    )

    result = extract_from_chunks(chunks)

    conclusion = _field(result, "conclusion")
    assert conclusion.status == "low_confidence"
    assert conclusion.value == ""
    assert conclusion.candidates, "应记录候选句供待审"
    assert conclusion.reason == "indicator_not_found_using_abstract_fallback"


def test_span_not_located_degrades_to_low_confidence():
    # 防御路径：证据句无法在 chunk 文本中定位（模拟篡改/外部注入）时，
    # _locate_sentence 返回 None，调用方必须降级而非编造。
    assert _locate_sentence("真实 chunk 文本。", "不存在的句子") is None
    assert _locate_sentence("真实 chunk 文本。", "真实 chunk 文本。") == {
        "start_char": 0,
        "end_char": len("真实 chunk 文本。"),
    }


def test_span_tampering_does_not_fabricate():
    # 评审复现：在旧 chunk 前注入伪造结果句并保留旧 chunk_uid。
    chunks = _chunks_for()
    tampered = [dict(chunk) for chunk in chunks]
    target = next(c for c in tampered if c["chunk_type"] == "full_text")
    target["text"] = "Results show the fabricated treatment achieves 99% accuracy. " + target["text"]

    result = extract_from_chunks(tampered)

    # HIGH-1：来源链断裂（chunk_uid 重算不一致）→ 记入 invalid_chunks，禁止参与抽取。
    assert any(
        c["chunk_uid"] == target["chunk_uid"] and c["reason"] == "chunk_uid_mismatch"
        for c in result.invalid_chunks
    )
    # 被篡改 chunk 不得再产出任何确定字段（不允许保持 extracted）。
    for f in result.fields:
        if f.evidence is not None and f.evidence.chunk_uid == target["chunk_uid"]:
            assert f.status != "extracted", f"{f.field} 不应从被篡改 chunk 保持 extracted"
    # 注入的伪造结果句不得成为任何字段值（不编造）。
    values = [f.value for f in result.fields if isinstance(f.value, str)]
    assert not any("fabricated" in v.lower() for v in values)


# --- 评审修复：跨来源聚合 / 确定性 / 换行切句 / 无时间戳 -----------------------


def test_cross_source_same_paper_id_not_merged(tmp_path):
    from src.data_contracts.admission import compute_record_hash

    records = []
    for source, abstract in [
        ("s1", "In this randomized trial we studied 50 participants. Results show 92% accuracy."),
        ("s2", "A limitation of our cohort is the small sample size."),
    ]:
        record = {
            "paper_id": "P1",
            "source": source,
            "license": "cc0",
            "language": "zh",
            "year": 2024,
            "usage_rights": "indexable",
            "source_file_sha256": "f" * 64,
            "title": f"Paper from {source}",
            "abstract": abstract,
            "full_text": "",
        }
        record["record_sha256"] = compute_record_hash(record)
        records.append(record)

    chunk_lines = []
    for record in records:
        for chunk in build_traceable_chunks(record).chunks:
            chunk_lines.append(json.dumps(chunk, ensure_ascii=False, sort_keys=True))
    chunks_path = tmp_path / "chunks.jsonl"
    chunks_path.write_text("\n".join(chunk_lines) + "\n", encoding="utf-8")

    summary = run_structured_extraction(input_chunks_path=chunks_path, output_dir=tmp_path / "out")

    # HIGH-2：不同来源同名 paper_id 必须分开（papers_processed=2，输出两篇）。
    assert summary["papers_processed"] == 2
    results = [
        json.loads(line)
        for line in (tmp_path / "out" / "structured.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(results) == 2
    assert {r["source"] for r in results} == {"s1", "s2"}
    s1 = next(r for r in results if r["source"] == "s1")
    s2 = next(r for r in results if r["source"] == "s2")
    assert any(f["status"] == "extracted" for f in s1["fields"])
    assert any(f["status"] == "extracted" for f in s2["fields"])


def test_input_ordering_does_not_change_extraction():
    chunks = _chunks_for()
    reversed_chunks = list(reversed(chunks))

    forward = extract_from_chunks(chunks)
    backward = extract_from_chunks(reversed_chunks)

    assert forward.paper_id == backward.paper_id
    assert [
        (f.field, f.status, f.value, f.evidence.chunk_uid if f.evidence else None)
        for f in forward.fields
    ] == [
        (f.field, f.status, f.value, f.evidence.chunk_uid if f.evidence else None)
        for f in backward.fields
    ]


def test_newline_splits_sentences():
    sentences = _split_sentences(
        "Title without punctuation\nAbstract first sentence. Second sentence."
    )
    assert sentences == ["Title without punctuation", "Abstract first sentence.", "Second sentence."]


def test_structured_output_has_no_timestamp():
    chunks = _chunks_for()
    payload = _result_to_dict(extract_from_chunks(chunks))
    assert "extracted_at" not in payload  # 确定性输出
    assert payload["schema_version"] == SCHEMA_VERSION


# --- 端到端：D02 小样例 -----------------------------------------------------


def test_end_to_end_with_d02_sample(tmp_path):
    from src.data_contracts.admission import compute_record_hash

    records = []
    for idx, abstract in enumerate(
        [
            "In this randomized trial, we studied 50 participants. Results show 92% accuracy. "
            "A limitation is the small cohort. In conclusion, we suggest wider validation.",
            "This is a background note without design, results, or conclusions.",
        ]
    ):
        record = {
            "paper_id": f"PX-E{idx}",
            "source": "iflytek",
            "license": "cc0",
            "language": "zh",
            "year": 2024,
            "usage_rights": "indexable",
            "source_file_sha256": "f" * 64,
            "title": f"Paper {idx}",
            "abstract": abstract,
            "full_text": "",
        }
        record["record_sha256"] = compute_record_hash(record)
        records.append(record)

    # D02：切为 traceable chunks。
    chunks_dir = tmp_path / "traceable"
    chunk_lines = []
    for record in records:
        for chunk in build_traceable_chunks(record).chunks:
            chunk_lines.append(json.dumps(chunk, ensure_ascii=False, sort_keys=True))
    chunks_path = chunks_dir / "chunks.jsonl"
    chunks_path.parent.mkdir(parents=True, exist_ok=True)
    chunks_path.write_text("\n".join(chunk_lines) + "\n", encoding="utf-8")

    # D03：端到端抽取。
    summary = run_structured_extraction(input_chunks_path=chunks_path, output_dir=tmp_path / "out")

    assert summary["schema_version"] == SCHEMA_VERSION
    assert summary["papers_processed"] == 2
    assert summary["invalid_chunks"] == 0  # 测试数据无篡改
    assert "extracted_at" in summary  # 时间戳移到运行级 summary
    results = [
        json.loads(line)
        for line in (tmp_path / "out" / "structured.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert all("extracted_at" not in line for line in results)  # 行级输出确定性
    assert {r["paper_id"] for r in results} == {"PX-E0", "PX-E1"}
    extracted_fields = {
        paper["paper_id"]: {f["field"] for f in paper["fields"] if f["status"] == "extracted"}
        for paper in results
    }
    assert "main_result" in extracted_fields["PX-E0"]
    assert "conclusion" in extracted_fields["PX-E0"]
    # 无指示词的论文不产出确定值。
    assert not extracted_fields["PX-E1"] or all(
        f["status"] != "extracted"
        for f in next(r for r in results if r["paper_id"] == "PX-E1")["fields"]
    )
