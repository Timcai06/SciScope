"""LLM-assisted evidence chat API.

Contract summary:
- Input: ``ChatRequest`` with non-empty question and optional history.
- Output: ``ChatResponse`` containing answer text plus evidence excerpts.
- All requests are answered against the currently-loaded corpus in-memory.
"""

from fastapi import APIRouter, HTTPException, Request

from backend.app.core.budget import enforce_anonymous_rate_limit, enforce_chat_budget
from backend.app.core.config import get_settings
from backend.app.models.schemas import ChatRequest, ChatResponse
from backend.app.services.corpus_service import get_corpus
from backend.app.services.evidence_chat import answer_question

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
def chat(request: ChatRequest, http_request: Request) -> ChatResponse:
    """Answer a user question from corpus evidence.

    Return fields:
    - ``answer``: natural language response
    - ``evidence``: snippet-level supporting items
    - ``confidence`` and graph context fields for downstream ranking/UI rendering
    """
    # `/api/chat` is lighter than the full agent loop but still calls the hosted
    # LLM, so it shares the same public-edge budget guard as `/api/agent`.
    settings = get_settings()
    violation = enforce_chat_budget(
        request,
        max_question_chars=settings.agent_max_question_chars,
        max_history_turns=settings.agent_max_history_turns,
    )
    if violation is None:
        forwarded = http_request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
        if settings.trust_proxy_headers and forwarded:
            rate_key = forwarded
        elif http_request.client and http_request.client.host:
            rate_key = http_request.client.host
        else:
            rate_key = "anonymous"
        violation = enforce_anonymous_rate_limit(
            rate_key,
            requests_per_minute=settings.anon_requests_per_minute,
        )
    if violation is not None:
        raise HTTPException(
            status_code=429 if violation.code == "rate_limited" else 400,
            detail={"code": violation.code, "message": violation.message},
        )

    history = [{"role": t.role, "content": t.content} for t in request.history]
    return answer_question(request.question, get_corpus(), history=history)
