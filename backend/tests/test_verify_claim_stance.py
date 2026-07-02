"""verify_claim stance layer: a claim and its negation get different verdicts.

Step 0 pinned the defect (cosine grading is symmetric to negation, so both landed
"强支持"). Step 1 added a stance layer: after retrieval, the LLM judges each
evidence's stance toward the claim (SUPPORT / CONTRADICT / NEUTRAL) and the verdict
is derived from those labels. This file is now the green gate for that behavior.

The LLM judge (`verify_claim._judge_stances`) is mocked so the test is offline and
deterministic — the claim's evidence reads as SUPPORT, the negation's as CONTRADICT
(same papers, opposite stance), which is exactly the case cosine could not tell
apart.
"""

from __future__ import annotations

import json
import math
from types import SimpleNamespace

import pytest

from backend.app.agent.tools import verify_claim

# A claim the (fake) literature supports, and its direct negation. Both are about
# the same topic, so a real retriever returns the same papers for either.
CLAIM = "咖啡能降低心脏病风险"
NEGATION = "咖啡会增加心脏病风险"

# Top claim<->evidence cosine each lands at — both clear the 0.84 "强支持" bar,
# which is why similarity alone (Step 0) could not separate them.
_TOP_SIM = {CLAIM: 0.90, NEGATION: 0.88}


class _FakeEmbedder:
    """Embeds into R^2 so claim<->evidence dot product is a chosen value.

    Evidence anchors at unit vector [1, 0]; a claim with target similarity s
    encodes to [s, sqrt(1-s^2)], so dot(claim, evidence) == s exactly.
    """

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


def _fake_judge(claim: str, evidence_texts: list[str]) -> list[str]:
    """Stand-in for the LLM judge: SUPPORT for the claim, CONTRADICT for its negation."""
    label = "SUPPORT" if claim == CLAIM else "CONTRADICT"
    return [label for _ in evidence_texts]


@pytest.fixture
def _patched(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.app.services import retrieval_service
    from src.models import embeddings

    monkeypatch.setattr(retrieval_service, "search", _fake_search)
    monkeypatch.setattr(embeddings, "get_embedder", lambda *_a, **_k: _FakeEmbedder(_TOP_SIM))
    monkeypatch.setattr(verify_claim, "_judge_stances", _fake_judge)


def _result(claim: str) -> dict:
    """Drive the generator handler and return verify_claim's parsed payload."""
    gen = verify_claim.run({"claim": claim})
    result = None
    try:
        while True:
            next(gen)
    except StopIteration as stop:
        result = stop.value
    return json.loads(result)


def test_supported_claim_is_graded_strong(_patched: None) -> None:
    # Supporting evidence + high grounding similarity → 强支持 (backward compatible).
    assert _result(CLAIM)["支持等级"] == "强支持"


def test_negation_gets_different_verdict_from_claim(_patched: None) -> None:
    # The crack from Step 0 is closed: a claim and its negation, from the same
    # evidence, must not receive the same verdict.
    claim_verdict = _result(CLAIM)["支持等级"]
    negation = _result(NEGATION)
    assert negation["支持等级"] != claim_verdict
    assert negation["支持等级"] == "证据反驳"
    assert negation["证据立场统计"]["反驳"] == 1


def test_falls_back_to_similarity_when_judge_unavailable(
    _patched: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Fail-safe: with no usable LLM judge (offline / mock mode), the tool must not
    # crash — it falls back to the legacy similarity-only verdict.
    monkeypatch.setattr(verify_claim, "_judge_stances", lambda *_a, **_k: None)
    result = _result(CLAIM)
    assert result["判定方式"] == "similarity"
    assert result["支持等级"] == "强支持"
