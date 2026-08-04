"""Gold v1 workflow: blind packets, reconciliation, and non-fake labels."""

from __future__ import annotations

from evaluation.stance import annotation


def _candidates():
    return [
        {"id": "a", "claim": "Coffee lowers risk", "evidence": "Coffee lowered risk in this cohort.", "language": "en", "source": "doi:example/a"},
        {"id": "b", "claim": "咖啡提高风险", "evidence": "该研究未观察到风险升高。", "language": "zh", "source": "doi:example/b"},
    ]


def test_packets_are_blind_and_independently_ordered() -> None:
    first, second = annotation.packet_rows(_candidates(), seed=7)
    assert {row["id"] for row in first} == {"a", "b"}
    assert all(row["stance"] == "" and "label" not in row for row in second)
    assert first != second


def test_reconciliation_sends_sentence_disagreement_to_expert() -> None:
    candidates = _candidates()
    first, second = annotation.packet_rows(candidates, seed=7)
    for row in first + second:
        if row["id"] == "a":
            row.update({"stance": "SUPPORT", "evidence_sentence": "Coffee lowered risk in this cohort."})
        else:
            row.update({"stance": "CONTRADICT", "evidence_sentence": "该研究未观察到风险升高。"})
    second[0]["evidence_sentence"] = ""  # invalid disagreement must not become gold
    try:
        annotation.reconcile(candidates, first, second)
    except ValueError as exc:
        assert "requires a verbatim" in str(exc)
    else:
        raise AssertionError("non-neutral annotation without evidence sentence must fail")


def test_reconciliation_keeps_exact_agreement() -> None:
    candidates = _candidates()
    first, second = annotation.packet_rows(candidates, seed=7)
    for packet in (first, second):
        for row in packet:
            if row["id"] == "a":
                row.update({"stance": "SUPPORT", "evidence_sentence": "Coffee lowered risk in this cohort."})
            else:
                row.update({"stance": "CONTRADICT", "evidence_sentence": "该研究未观察到风险升高。"})
    agreed, queue = annotation.reconcile(candidates, first, second)
    assert len(agreed) == 2
    assert queue == []
