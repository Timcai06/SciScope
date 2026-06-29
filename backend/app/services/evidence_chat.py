"""Question-answering service for literature-grounded chat.

Boundary:
  - Accepts a user question and optional in-memory papers.
  - Builds evidence, prompts the configured LLM provider, and returns
    `ChatResponse` with citations + confidence.
  - Does not write to corpus or model state; it only orchestrates retrieval and
    prompt assembly.

Fallback model:
  - DB + `retrieval_service` when available and requested.
  - Deterministic in-memory lexical matcher when DB route is off or unreachable.
"""
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


# Comparative / temporal questions that benefit from multi-hop decomposition.
_MULTIHOP = ("对比", "比较", "区别", "差异", "相比", "异同", " vs ", "versus",
             "compare", "comparison", "difference between", "演进", "演变",
             "发展历程", "发展趋势", "变化趋势", "evolution of", "evolve")
_MULTIHOP_EVIDENCE_CAP = 6


def _is_multihop(question: str) -> bool:
    """Detect comparative / temporal questions that benefit from decomposition."""
    q = question.lower()
    return any(m in q for m in _MULTIHOP)


def _plan_subqueries(question: str, llm: LLMProvider) -> list[str]:
    """Decompose a comparative/temporal question into focused retrieval sub-queries.

    Comparative questions ("A 和 B 的区别") retrieve poorly as one query — one side
    dominates. We ask the LLM to split into 1-3 sub-queries so each facet gets its
    own evidence. Falls back to the original question on any failure.
    """
    chinese = _is_chinese(question)
    if chinese:
        prompt = (
            "把下面的科研问题分解成 1-3 个用于文献检索的子查询(对比类问题拆成各个方面,"
            "演进类问题拆成不同阶段/方向),每行一个,只输出子查询本身,不要编号、解释或多余文字。\n\n"
            f"问题:{question}\n\n子查询:"
        )
    else:
        prompt = (
            "Decompose the research question into 1-3 focused retrieval sub-queries "
            "(split comparisons into each side). One per line, output only the sub-queries.\n\n"
            f"Question: {question}\n\nSub-queries:"
        )
    try:
        out = llm.complete(prompt)
    except Exception:
        return [question]
    subs = []
    for line in out.splitlines():
        s = line.strip().lstrip("-*·•0123456789.、) ").strip()
        if len(s) >= 2 and s.lower() not in ("sub-queries", "子查询"):
            subs.append(s)
    subs = subs[:3]
    return subs or [question]


def answer_question(
    question: str,
    papers: list[dict[str, Any]],
    provider: LLMProvider | None = None,
    history: list[dict] | None = None,
    retrieval: str = "auto",
) -> ChatResponse:
    """Answer a question over evidence.

    ``retrieval`` makes the data-source an explicit contract rather than a hidden
    runtime sniff:
      * ``"auto"`` (default): use the hybrid DB/pgvector backend if reachable,
        else fall back to the in-memory ``papers`` matcher.
      * ``"db"``: require the hybrid backend.
      * ``"memory"``: always use the in-memory ``papers`` matcher (deterministic;
        used by hermetic unit tests over the sample corpus).

    Contract notes:
      - `question` is used both for retrieval and user-facing answer drafting.
      - `history` only affects query rewriting and prompt context, not final filtering.
      - `provider` can be injected to bypass global provider selection.
    """
    entities: list[str] = []
    neighbors: list[str] = []
    evidence = None
    retrieval_q = _retrieval_query(question, history)
    llm = provider or get_llm_provider()
    use_db = retrieval == "db" or (retrieval == "auto" and retrieval_service.is_available())
    if use_db:
        # GraphRAG: expand each query along the keyword co-occurrence graph so the
        # knowledge graph actively participates in retrieval (query expansion).
        from backend.app.services import graphrag

        # Multi-hop: split comparative/temporal questions into sub-queries and
        # merge their evidence so both sides of a comparison are represented.
        multihop = _is_multihop(question)
        subqueries = _plan_subqueries(question, llm) if multihop else [retrieval_q]
        per = EVIDENCE_LIMIT if len(subqueries) == 1 else max(2, _MULTIHOP_EVIDENCE_CAP // len(subqueries))
        evidence = []
        seen_ids: set[str] = set()
        for sq in subqueries:
            expansion = graphrag.expand(sq)
            if not entities:
                entities, neighbors = expansion.entities, expansion.neighbours
            search_query = graphrag.expanded_query(sq, expansion)
            for item in retrieval_service.search(search_query, limit=per):
                if item.paper_id in seen_ids:
                    continue
                seen_ids.add(item.paper_id)
                evidence.append(_to_evidence(item))
        evidence = evidence[:_MULTIHOP_EVIDENCE_CAP]
    if evidence is None:
        # Fallback: use deterministic in-memory matcher for sample corpus or DB-offline mode.
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
    if (
        not answer.strip()
        or not evidence_text.strip()
        or not retrieval_service.runtime_embeddings_enabled()
        or not retrieval_service.is_available()
    ):
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
    """Deterministic fallback retrieval used when DB route is disabled.

    It performs lightweight lexical matching over paper title/keywords/abstract/full_text
    and is intentionally stable for tests and offline operation.
    """
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
    """Build a short evidence-only prompt while keeping language consistency.

    The prompt always asks for citation-style references `[n]` so callers can map
    answer claims back to returned evidence rows.
    """
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
    """Score one in-memory paper candidate with term, phrase, and keyword boosts."""
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
