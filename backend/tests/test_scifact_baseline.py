"""Unit contracts for the non-L3 SciFact baseline helpers."""

from evaluation.stance import scifact_baseline


def test_document_pair_labels_do_not_use_claim_level_evidence() -> None:
    claim = {
        "evidence": {
            "1": [{"label": "SUPPORT", "sentences": [0]}],
            "2": [{"label": "CONTRADICT", "sentences": [1]}],
        }
    }
    assert scifact_baseline._claim_document_label(claim, 1) == "SUPPORT"
    assert scifact_baseline._claim_document_label(claim, 2) == "CONTRADICT"
    assert scifact_baseline._claim_document_label(claim, 3) == "NEUTRAL"


def test_top_sentences_is_deterministic_and_caps_at_three() -> None:
    document = {
        "title": "Example",
        "abstract": [
            "Unrelated introduction.",
            "Coffee intake reduces cardiovascular risk.",
            "Coffee is measured in the cohort.",
            "A final unrelated sentence.",
        ],
    }
    assert scifact_baseline._top_sentences("Coffee reduces cardiovascular risk.", document) == [1, 2, 0]
