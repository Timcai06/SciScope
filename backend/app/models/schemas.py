from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    question: str = Field(min_length=1)

    @field_validator("question")
    @classmethod
    def strip_question(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("question must not be empty")
        return stripped


class YearRange(BaseModel):
    start: int | None
    end: int | None


class TrendPoint(BaseModel):
    year: int
    count: int


class FieldCount(BaseModel):
    field: str
    count: int


class KeywordCount(BaseModel):
    keyword: str
    count: int


class CollaborationEdge(BaseModel):
    source: str
    target: str
    weight: int


class EvidenceItem(BaseModel):
    paper_id: str
    title: str
    year: int | None
    reason: str


class ChatResponse(BaseModel):
    answer: str
    evidence: list[EvidenceItem]
    confidence: str


class IngestStatusResponse(BaseModel):
    status: Literal["ready"]
    papers: int


class DashboardResponse(BaseModel):
    total_papers: int
    year_range: YearRange
    publication_trend: list[TrendPoint]
    field_distribution: list[FieldCount]
    top_keywords: list[KeywordCount]
    collaboration_edges: list[CollaborationEdge]
