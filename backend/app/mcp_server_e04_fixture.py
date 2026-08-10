"""E04 fixture MCP server for deterministic OpenCode write-then-read proof.

Purpose:
  - Provide a controlled SciScope MCP environment where OpenCode can execute a
    real ``verify_claim(persist=true)`` tool call and then read
    ``sciscope://disputes/recent``.
  - Keep the proof honest: retrieval and stance judgement are deterministic
    fixtures, so this server proves MCP/tool/resource/database semantics only.
    It is not evidence of natural-corpus stance quality.

The runtime still uses the real ``verify_claim`` tool implementation and the
real stance store / contradictions view. Only three inputs are patched:
  1) retrieval candidates
  2) embedder vectors
  3) stance judge output
"""

from __future__ import annotations

import math
from types import SimpleNamespace

from backend.app.agent.tools import verify_claim
from backend.app.services import retrieval_service
from backend.app.services.stance import judge as stance_judge
from src.models import embeddings

FIXTURE_CLAIM = "E04 fixture coffee lowers cardiovascular risk"
FIXTURE_PAPER_IDS = ["E04-SUPPORT", "E04-CONTRADICT"]


class _FixtureEmbedder:
    def encode_query(self, _text: str) -> list[float]:
        return [1.0, 0.0]

    def encode_passages(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            score = 0.95 if "lower" in text else 0.90
            vectors.append([score, math.sqrt(1 - score**2)])
        return vectors


def _fixture_search(_query: str, limit: int = 6) -> list[SimpleNamespace]:
    return [
        SimpleNamespace(
            paper_id=FIXTURE_PAPER_IDS[0],
            title="Fixture support paper",
            year=2023,
            snippet="Coffee intake was associated with lower cardiovascular risk.",
        ),
        SimpleNamespace(
            paper_id=FIXTURE_PAPER_IDS[1],
            title="Fixture contradict paper",
            year=2022,
            snippet="Coffee intake was associated with higher cardiovascular risk.",
        ),
    ][:limit]


def _fixture_judge(_claim: str, _texts: list[str]) -> stance_judge.JudgeResult:
    return stance_judge.JudgeResult(
        ok=True,
        judgements=[
            stance_judge.EvidenceJudgement(
                "SUPPORT",
                0.95,
                "Coffee intake was associated with lower cardiovascular risk.",
                None,
            ),
            stance_judge.EvidenceJudgement(
                "CONTRADICT",
                0.90,
                "Coffee intake was associated with higher cardiovascular risk.",
                None,
            ),
        ],
    )


def install_fixture(monkeypatch=None) -> None:
    """Install fixture dependencies, optionally with pytest-managed rollback."""
    embedder_factory = lambda *_args, **_kwargs: _FixtureEmbedder()
    if monkeypatch is not None:
        monkeypatch.setattr(retrieval_service, "search", _fixture_search)
        monkeypatch.setattr(embeddings, "get_embedder", embedder_factory)
        monkeypatch.setattr(verify_claim, "_judge_stances", _fixture_judge)
        return
    retrieval_service.search = _fixture_search
    embeddings.get_embedder = embedder_factory
    verify_claim._judge_stances = _fixture_judge


def main() -> None:
    install_fixture()
    from backend.app import mcp_server

    mcp_server.main()


if __name__ == "__main__":
    main()
