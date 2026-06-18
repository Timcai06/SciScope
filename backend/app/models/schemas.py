from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(min_length=1)


class EvidenceItem(BaseModel):
    paper_id: str
    title: str
    year: int | None
    reason: str


class ChatResponse(BaseModel):
    answer: str
    evidence: list[EvidenceItem]
    confidence: str


class DashboardResponse(BaseModel):
    total_papers: int
    year_range: dict[str, int | None]
    publication_trend: list[dict[str, Any]]
    field_distribution: list[dict[str, Any]]
    top_keywords: list[dict[str, Any]]
    collaboration_edges: list[dict[str, Any]]
