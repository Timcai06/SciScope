"""LLM-assisted evidence chat API.

Contract summary:
- Input: ``ChatRequest`` with non-empty question and optional history.
- Output: ``ChatResponse`` containing answer text plus evidence excerpts.
- All requests are answered against the currently-loaded corpus in-memory.
"""

from fastapi import APIRouter

from backend.app.models.schemas import ChatRequest, ChatResponse
from backend.app.services.corpus_service import get_corpus
from backend.app.services.evidence_chat import answer_question

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    """Answer a user question from corpus evidence.

    Return fields:
    - ``answer``: natural language response
    - ``evidence``: snippet-level supporting items
    - ``confidence`` and graph context fields for downstream ranking/UI rendering
    """
    history = [{"role": t.role, "content": t.content} for t in request.history]
    return answer_question(request.question, get_corpus(), history=history)
