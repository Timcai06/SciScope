"""Offline tests for A03 QA regression harness."""

from __future__ import annotations

import json

from evaluation import eval_qa_regression
from evaluation.qa_regression_fixture import CATEGORY_RULES, PRIMARY_CASES, SHADOW_FAILURE_CASES


def test_primary_suite_passes_and_keeps_category_counts() -> None:
    report = eval_qa_regression.run(output_path=_tmp_output("primary.json"))
    assert report["primary_passed"] == report["primary_total"] == len(PRIMARY_CASES)
    assert report["shadow_detected"] == report["shadow_total"] == len(SHADOW_FAILURE_CASES)
    assert report["sample_counts"]["citation_integrity"] == 2
    assert report["sample_counts"]["evidence_insufficient"] == 1


def test_category_summary_uses_frozen_rules() -> None:
    report = eval_qa_regression.run(output_path=_tmp_output("summary.json"))
    summary = {item["category"]: item for item in report["category_summary"]}
    assert summary["confirmation_bias"]["rule"] == CATEGORY_RULES["confirmation_bias"]
    assert summary["dependency_failure"]["samples"] == 1


def test_manual_review_template_remains_blank_for_human_fields() -> None:
    report = eval_qa_regression.run(output_path=_tmp_output("manual.json"))
    row = next(item for item in report["manual_review_rows"] if item["case_id"] == "confirmation-bias-honest-abstention")
    assert row["manual_support_judgement"] == ""
    assert row["manual_citation_precision"] == ""
    assert row["expected_status"] == "evidence_insufficient"


def test_shadow_failures_are_detected_without_counting_as_primary_failures() -> None:
    report = eval_qa_regression.run(output_path=_tmp_output("shadow.json"))
    shadow = {item["case_id"]: item for item in report["shadow_results"]}
    assert shadow["shadow-confirmation-bias-overclaim"]["detected"] is True
    assert shadow["shadow-temporal-overclaim-2027"]["detected"] is True
    assert shadow["shadow-causality-overclaim"]["detected"] is True


def test_report_files_are_written() -> None:
    output = _tmp_output("files.json")
    eval_qa_regression.run(output_path=output)
    assert output.exists()
    assert output.with_suffix(".md").exists()
    manual = output.parent / "qa_regression_manual_review_template.jsonl"
    assert manual.exists()
    rows = [json.loads(line) for line in manual.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == len(PRIMARY_CASES)


def test_primary_case_contract_details_match_expected_boundaries() -> None:
    report = eval_qa_regression.run(output_path=_tmp_output("contracts.json"))
    primary = {item["case_id"]: item for item in report["primary_results"]}
    assert primary["citation-missing-title-year"]["contract"]["citation_compliance"] == "missing_required_citations"
    assert primary["time-boundary-2026"]["contract"]["status"] == "not_found"
    assert "相关性不等于因果" in primary["correlation-not-causation"]["contract"]["uncertainty"]["qualification_hints"]
    assert primary["dependency-failure-explicit"]["contract"]["status"] == "dependency_failure"


def _tmp_output(name: str):
    from pathlib import Path
    import tempfile

    return Path(tempfile.gettempdir()) / name
