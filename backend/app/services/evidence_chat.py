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
    if not evidence:
        return ChatResponse(
            answer="No matching evidence found for this question in the current corpus.",
            evidence=[],
            confidence="low",
        )

    prompt = _build_prompt(question, evidence)
    llm = provider or get_llm_provider()
    answer = llm.complete(prompt)

    return ChatResponse(answer=answer, evidence=evidence, confidence="medium")


def _retrieve_evidence(
    question: str,
    papers: list[dict[str, Any]],
    limit: int,
) -> list[EvidenceItem]:
    query_terms = _text_terms(question)
    query_phrases = _query_phrases(question)
    special_phrases = _special_query_phrases(query_terms)
    ranked: list[tuple[int, int, EvidenceItem]] = []

    for index, paper in enumerate(papers):
        score, matches = _score_paper(query_terms, query_phrases, special_phrases, paper)
        if score <= 0:
            continue

        ranked.append(
            (
                score,
                -index,
                EvidenceItem(
                    paper_id=str(paper.get("paper_id", "")),
                    title=str(paper.get("title", "")),
                    year=paper.get("year"),
                    reason=f"Matched evidence: {', '.join(matches)}",
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


def _text_terms(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


def _query_phrases(question: str) -> set[str]:
    tokens = _TOKEN_RE.findall(question.lower())
    phrases: set[str] = set()
    for size in (2, 3):
        phrases.update(
            " ".join(tokens[index : index + size]) for index in range(len(tokens) - size + 1)
        )
    return phrases


def _special_query_phrases(query_terms: set[str]) -> set[str]:
    if "rag" in query_terms:
        return {"retrieval augmented generation"}
    return set()


def _score_paper(
    query_terms: set[str],
    query_phrases: set[str],
    special_phrases: set[str],
    paper: dict[str, Any],
) -> tuple[int, list[str]]:
    fields = {
        "title": str(paper.get("title", "")),
        "keywords": " ".join(str(keyword) for keyword in paper.get("keywords", [])),
        "abstract": str(paper.get("abstract", "")),
        "full_text": str(paper.get("full_text", "")),
    }
    field_weights = {
        "title": 60,
        "keywords": 50,
        "abstract": 20,
        "full_text": 10,
    }
    phrase_multipliers = {
        "title": 4,
        "keywords": 4,
        "abstract": 3,
        "full_text": 2,
    }

    score = 0
    direct_hits: set[str] = set()
    exact_phrase_hits: set[str] = set()
    special_phrase_hits: set[str] = set()

    for field_name, field_text in fields.items():
        normalized_text = _normalize_text(field_text)
        field_terms = _text_terms(field_text)
        terms = query_terms & field_terms
        if terms:
            direct_hits.update(terms)
            score += len(terms) * field_weights[field_name]

        phrases = {phrase for phrase in query_phrases if _contains_phrase(normalized_text, phrase)}
        if phrases:
            exact_phrase_hits.update(phrases)
            score += len(phrases) * field_weights[field_name] * phrase_multipliers[field_name]

        specials = {phrase for phrase in special_phrases if _contains_phrase(normalized_text, phrase)}
        if specials:
            special_phrase_hits.update(specials)
            score += len(specials) * field_weights[field_name] * phrase_multipliers[field_name] * 2

    if not (direct_hits or exact_phrase_hits or special_phrase_hits):
        return 0, []

    matches = [*sorted(special_phrase_hits), *sorted(exact_phrase_hits), *sorted(direct_hits)]
    return score, matches


def _normalize_text(text: str) -> str:
    return " ".join(_TOKEN_RE.findall(text.lower()))


def _contains_phrase(normalized_text: str, phrase: str) -> bool:
    return f" {phrase} " in f" {normalized_text} "
