from fastapi import APIRouter

from backend.app.models.schemas import ChatRequest, ChatResponse
from backend.app.services.corpus_service import get_corpus
from backend.app.services.evidence_chat import answer_question

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    history = [{"role": t.role, "content": t.content} for t in request.history]
    return answer_question(request.question, get_corpus(), history=history)
