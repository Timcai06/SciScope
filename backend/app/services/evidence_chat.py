import re
from typing import Any

from backend.app.models.schemas import ChatResponse, EvidenceItem
from backend.app.services import retrieval_service
from backend.app.services.deepseek_provider import LLMProvider, get_llm_provider

EVIDENCE_LIMIT = 3
_TOKEN_RE = re.compile(r"[a-z0-9]+")


# Explicit reference/anaphora markers — only these trigger context prepend, so a
# short *new-topic* follow-up ("大语言模型呢") is NOT merged with the old topic.
_ANAPHORA = ("它", "它们", "他们", "这个", "这些", "那个", "那些", "上述", "上面",
             "前面", "刚才", "该方法", "继续", "还有呢", "其中",
             "its", " it ", " it?", "they", "them", "this one", "those", "the above", "keep going")


def _retrieval_query(question: str, history: list[dict] | None) -> str:
    """Resolve anaphoric follow-ups by prepending the previous user topic.

    Only triggers on explicit reference words; a short query that names a new
    topic is left as-is so its topic is not diluted by the prior turn.
    """
    if not history:
        return question
    q = question.strip()
    last_user = next((h["content"] for h in reversed(history) if h.get("role") == "user"), "")
    if not last_user:
        return question
    ql = " " + q.lower() + " "
    anaphoric = any(a in (q if "一" <= a[0] <= "鿿" else ql) for a in _ANAPHORA)
    return f"{last_user} {question}" if anaphoric else question


def answer_question(
    question: str,
    papers: list[dict[str, Any]],
    provider: LLMProvider | None = None,
    history: list[dict] | None = None,
) -> ChatResponse:
    entities: list[str] = []
    neighbors: list[str] = []
    evidence = None
    retrieval_q = _retrieval_query(question, history)
    if retrieval_service.is_available():
        # GraphRAG: expand the query along the keyword co-occurrence graph so the
        # knowledge graph actively participates in retrieval (query expansion).
        from backend.app.services import graphrag

        expansion = graphrag.expand(retrieval_q)
        entities, neighbors = expansion.entities, expansion.neighbours
        search_query = graphrag.expanded_query(retrieval_q, expansion)
        evidence = [
            _to_evidence(item) for item in retrieval_service.search(search_query, limit=EVIDENCE_LIMIT)
        ]
    if evidence is None:
        # Fall back to the in-memory matcher (sample corpus / DB unavailable).
        evidence = _retrieve_evidence(retrieval_q, papers, limit=EVIDENCE_LIMIT)

    if not evidence:
        return ChatResponse(
            answer="No matching evidence found for this question in the current corpus.",
            evidence=[],
            confidence="low",
            graph_entities=entities,
            graph_neighbors=neighbors,
        )

    prompt = _build_prompt(question, evidence, history)
    llm = provider or get_llm_provider()
    answer = llm.complete(prompt)

    confidence = _verify_answer(answer, evidence)
    return ChatResponse(
        answer=answer,
        evidence=evidence,
        confidence=confidence,
        graph_entities=entities,
        graph_neighbors=neighbors,
    )


def _to_evidence(item) -> EvidenceItem:
    return EvidenceItem(
        paper_id=item.paper_id,
        title=item.title,
        year=item.year,
        reason=f"Matched via {', '.join(item.matched_by)} (score {item.score})",
        authors=item.authors,
        snippet=item.snippet,
    )


# Common words to ignore when measuring answer-evidence support.
_STOP = {
    "the", "a", "an", "of", "and", "or", "in", "on", "for", "to", "is", "are",
    "with", "by", "as", "that", "this", "from", "using", "based", "via", "can",
}


def _verify_answer(answer: str, evidence: list[EvidenceItem]) -> str:
    """Faithfulness check: is the answer supported by the evidence?

    Prefers a cross-lingual *semantic* match (embed answer vs evidence) so a
    correct Chinese answer grounded in English papers is not wrongly flagged.
    Falls back to lexical overlap + citation signal when the embedder is not
    available (e.g. unit tests / no DB).
    """
    cited = {int(m) for m in re.findall(r"\[(\d+)\]", answer) if 0 < int(m) <= len(evidence)}
    evidence_text = " ".join(f"{e.title} {e.snippet}" for e in evidence)

    sim = _semantic_support(answer, evidence_text)
    if sim is not None:
        if sim >= 0.80 or (sim >= 0.70 and cited):
            return "high"
        if sim >= 0.62 or cited:
            return "medium"
        return "low"

    # Lexical fallback (cross-lingual unaware) — citation also counts as grounding.
    answer_terms = {t for t in _text_terms(answer) if t not in _STOP and len(t) > 2}
    evidence_terms = _text_terms(evidence_text)
    supported = sum(1 for t in answer_terms if t in evidence_terms)
    support_ratio = supported / len(answer_terms) if answer_terms else 0.0
    if support_ratio >= 0.5 or (cited and support_ratio >= 0.2):
        return "high"
    if support_ratio >= 0.25 or cited:
        return "medium"
    return "low"


def _semantic_support(answer: str, evidence_text: str) -> float | None:
    """Cosine similarity between answer and evidence via the local embedder.

    Returns None when the embedder/service layer is unavailable so the caller
    can fall back to lexical scoring.
    """
    if not answer.strip() or not evidence_text.strip() or not retrieval_service.is_available():
        return None
    try:
        from src.models.embeddings import get_embedder

        emb = get_embedder()
        import numpy as np

        a = emb.encode_passages([answer[:1200]])[0]
        e = emb.encode_passages([evidence_text[:1500]])[0]
        return float(np.dot(a, e))  # both are L2-normalized
    except Exception:
        return None




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


def _is_chinese(text: str) -> bool:
    return any("一" <= ch <= "鿿" for ch in text)


def _history_block(history: list[dict] | None, chinese: bool) -> str:
    if not history:
        return ""
    recent = history[-4:]  # last 2 turns
    label_u, label_a = ("用户", "助手") if chinese else ("User", "Assistant")
    lines = [f"{label_u if h.get('role') == 'user' else label_a}: {h.get('content', '')}" for h in recent]
    header = "对话历史(供理解追问的上下文):" if chinese else "Conversation so far (context for follow-ups):"
    return header + "\n" + "\n".join(lines) + "\n\n"


def _build_prompt(question: str, evidence: list[EvidenceItem], history: list[dict] | None = None) -> str:
    evidence_lines = []
    for index, item in enumerate(evidence, start=1):
        snippet = (item.snippet or item.reason).strip()
        evidence_lines.append(
            f"[{index}] {item.title} ({item.year or 'unknown year'}): {snippet}"
        )
    evidence_block = "\n".join(evidence_lines) if evidence_lines else "- No matching evidence"
    chinese = _is_chinese(question)
    history_block = _history_block(history, chinese)
    if chinese:
        lang = "请用中文回答。"
        instruct = (
            "你是科研文献助手。结合对话历史理解当前问题,但仅依据下面的证据作答,用 [n] 标注引用。"
            "要综合归纳成 2-4 句话,不要照抄标题;证据不足时明确说明。"
        )
        tail = "基于证据的中文回答:"
    else:
        lang = "Answer in English."
        instruct = (
            "You are a research literature assistant. Use the conversation history to understand "
            "the current question, but answer using ONLY the evidence below, cite as [n]. "
            "Synthesize into 2-4 sentences; do not just copy titles. If evidence is insufficient, say so."
        )
        tail = "Grounded answer:"
    return f"{instruct} {lang}\n\n{history_block}Question: {question}\n\nEvidence:\n{evidence_block}\n\n{tail}"


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
