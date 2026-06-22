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
    authors: list[str] = Field(default_factory=list)
    snippet: str = ""


class ChatResponse(BaseModel):
    answer: str
    evidence: list[EvidenceItem]
    confidence: str
    graph_entities: list[str] = Field(default_factory=list)
    graph_neighbors: list[str] = Field(default_factory=list)


class SearchResultItem(BaseModel):
    paper_id: str
    title: str
    year: int | None
    field: str
    authors: list[str] = Field(default_factory=list)
    snippet: str = ""
    score: float
    matched_by: list[str] = Field(default_factory=list)


class SearchResponse(BaseModel):
    query: str
    count: int
    results: list[SearchResultItem]


class TrendKeyword(BaseModel):
    keyword: str
    doc_count: int | None = None
    normalized_df: float | None = None
    momentum_score: float | None = None
    burst_score: float | None = None
    trend_slope: float | None = None
    trend_r2: float | None = None
    forecast_year: int | None = None
    forecast_normalized_df: float | None = None
    forecast_low: float | None = None
    forecast_high: float | None = None
    trend_score: float | None = None
    lifecycle_stage: str | None = None
    representative_title: str | None = None
    representative_year: int | None = None


class TrendSeriesPoint(BaseModel):
    year: int
    normalized_df: float


class TrendsResponse(BaseModel):
    generated_at: str | None = None
    fit_years: list[int] = Field(default_factory=list)
    forecast_year: int | None = None
    method: str = ""
    uncertainty_note: str = ""
    top_hot: list[TrendKeyword] = Field(default_factory=list)
    top_emerging: list[TrendKeyword] = Field(default_factory=list)
    series: list[TrendSeriesPoint] = Field(default_factory=list)
    keyword: str | None = None


class Recommendation(BaseModel):
    paper_id: str
    title: str
    year: int | None
    field: str
    score: float
    semantic_similarity: float
    shared_keywords: list[str] = Field(default_factory=list)
    shared_authors: list[str] = Field(default_factory=list)
    factors: dict[str, float] = Field(default_factory=dict)


class RecommendResponse(BaseModel):
    paper_id: str
    count: int
    recommendations: list[Recommendation]


class GraphNode(BaseModel):
    id: str
    label: str | None = None

    model_config = {"extra": "allow"}


class GraphEdge(BaseModel):
    source: str
    target: str
    weight: int = 1


class GraphResponse(BaseModel):
    type: str
    center: str | None = None
    nodes: list[GraphNode]
    edges: list[GraphEdge]


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
