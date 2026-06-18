import re
from typing import Any

from backend.app.models.schemas import ChatResponse, EvidenceItem
from backend.app.services.deepseek_provider import LLMProvider, get_llm_provider

EVIDENCE_LIMIT = 3
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def answer_question(
    question: str,
    papers: list[dict[str, Any]],
    provider: LLMProvider | None = None,
) -> ChatResponse:
    evidence = _retrieve_evidence(question, papers, limit=EVIDENCE_LIMIT)
    prompt = _build_prompt(question, evidence)
    llm = provider or get_llm_provider()
    answer = llm.complete(prompt)

    return ChatResponse(answer=answer, evidence=evidence, confidence="medium")


def _retrieve_evidence(
    question: str,
    papers: list[dict[str, Any]],
    limit: int,
) -> list[EvidenceItem]:
    query_terms = _query_terms(question)
    ranked: list[tuple[int, int, EvidenceItem]] = []

    for index, paper in enumerate(papers):
        haystack_terms = _paper_terms(paper)
        overlap = query_terms & haystack_terms
        if not overlap:
            continue

        ranked.append(
            (
                len(overlap),
                -index,
                EvidenceItem(
                    paper_id=str(paper.get("paper_id", "")),
                    title=str(paper.get("title", "")),
                    year=paper.get("year"),
                    reason=f"Matched query terms: {', '.join(sorted(overlap))}",
                ),
            )
        )

    ranked.sort(reverse=True)
    return [item for _, _, item in ranked[:limit]]


def _build_prompt(question: str, evidence: list[EvidenceItem]) -> str:
    evidence_lines = [
        f"- {item.title} ({item.year or 'unknown year'}): {item.reason}" for item in evidence
    ]
    evidence_block = "\n".join(evidence_lines) if evidence_lines else "- No matching evidence"
    return f"Question: {question}\nEvidence:\n{evidence_block}\nAnswer with citations in mind."


def _query_terms(question: str) -> set[str]:
    terms = _text_terms(question)
    if "rag" in terms:
        terms.update({"retrieval", "augmented", "generation"})
    return terms


def _paper_terms(paper: dict[str, Any]) -> set[str]:
    keywords = paper.get("keywords", [])
    keyword_text = " ".join(str(keyword) for keyword in keywords)
    searchable_text = " ".join(
        [
            str(paper.get("title", "")),
            str(paper.get("abstract", "")),
            keyword_text,
            str(paper.get("full_text", "")),
        ]
    )
    return _text_terms(searchable_text)


def _text_terms(text: str) -> set[str]:
    tokens = set(_TOKEN_RE.findall(text.lower()))
    expanded = set(tokens)
    for token in tokens:
        if token.endswith("s") and len(token) > 4:
            expanded.add(token[:-1])
    return expanded
