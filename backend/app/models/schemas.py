"""Pydantic schemas used by SciScope public APIs.

These models are the executable API contract:
- request payload shapes (`...Request`)
- internal and response payload shapes (`...Response`)
- shared primitive entities (trend/search/recommend/graph rows)

Naming deliberately tracks endpoint contracts to keep frontend/backend expectations
stable and reviewable at the schema layer.
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ChatTurn(BaseModel):
    """Single turn in user/assistant conversation history."""

    role: Literal["user", "assistant"]
    content: str


class AgentRequest(BaseModel):
    """Agent input contract: question + optional chat history."""

    question: str = Field(min_length=1)
    history: list[ChatTurn] = Field(default_factory=list)

    @field_validator("question")
    @classmethod
    def strip_question(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("question must not be empty")
        return stripped


class ChatRequest(BaseModel):
    """Chat input contract for evidence-backed question answering."""

    question: str = Field(min_length=1)
    history: list[ChatTurn] = Field(default_factory=list)

    @field_validator("question")
    @classmethod
    def strip_question(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("question must not be empty")
        return stripped


class YearRange(BaseModel):
    """Closed year interval used by dashboard summary."""

    start: int | None
    end: int | None


class TrendPoint(BaseModel):
    """Single annual bucket in publication trend output."""

    year: int
    count: int


class FieldCount(BaseModel):
    """Field/cat histogram row."""

    field: str
    count: int


class KeywordCount(BaseModel):
    """Top keyword row with count in dashboard payload."""

    keyword: str
    count: int


class CollaborationEdge(BaseModel):
    """Undirected/coauthorship-style graph edge entry."""

    source: str
    target: str
    weight: int


class EvidenceItem(BaseModel):
    """Single evidence unit in chat answer context."""

    paper_id: str
    title: str
    year: int | None
    reason: str
    authors: list[str] = Field(default_factory=list)
    snippet: str = ""


class ChatResponse(BaseModel):
    """Structured response from chat route.

    - `evidence`: ordered evidence list supporting the answer.
    - `confidence`: service-defined confidence marker string.
    - graph fields are optional entity context for downstream visualization.
    """

    answer: str = Field(description="Final answer string for the question")
    evidence: list[EvidenceItem] = Field(description="Evidence references used in drafting answer")
    confidence: str = Field(description="Model/system confidence label")
    graph_entities: list[str] = Field(default_factory=list, description="Entity labels linked to the answer")
    graph_neighbors: list[str] = Field(default_factory=list, description="Neighbor entity labels for graph hints")


class SearchResultItem(BaseModel):
    """Single search hit in ``SearchResponse``."""

    paper_id: str
    title: str
    year: int | None
    field: str
    authors: list[str] = Field(default_factory=list)
    snippet: str = ""
    score: float
    matched_by: list[str] = Field(default_factory=list)


class SearchResponse(BaseModel):
    """Search endpoint response contract."""

    query: str = Field(description="Original query string used for retrieval")
    count: int = Field(description="Total hits materialized into response payload")
    results: list[SearchResultItem] = Field(description="List of retrieved items, up to request limit")


class TrendKeyword(BaseModel):
    """Single trend-row object for hot/emerging lists."""

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
    """Time-series point for single keyword trend display."""

    year: int
    normalized_df: float


class TrendsResponse(BaseModel):
    """Trend API response.

    `top_hot` and `top_emerging` are summary lists; `series` is present only when
    a keyword filter is supplied in request.
    """

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
    """One recommendation row in ``RecommendResponse``."""

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
    """Recommendation response for `/api/recommend`."""

    paper_id: str
    count: int
    recommendations: list[Recommendation]


class GraphNode(BaseModel):
    """Graph node entry from `/api/graph`."""

    id: str
    label: str | None = None

    model_config = {"extra": "allow"}


class GraphEdge(BaseModel):
    """Graph edge entry from `/api/graph`."""

    source: str
    target: str
    weight: int = 1


class GraphCommunity(BaseModel):
    """Optional graph community metadata."""

    community: float | int | str | None = None
    size: int
    top_terms: list[str] = Field(default_factory=list)


class GraphResponse(BaseModel):
    """Top-level graph contract for `/api/graph`."""

    type: str
    center: str | None = None
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    communities: list[GraphCommunity] = Field(default_factory=list)


class IngestStatusResponse(BaseModel):
    """Status contract for corpus ingestion/readiness endpoint."""

    status: Literal["ready"]
    papers: int


class DashboardResponse(BaseModel):
    """Dashboard aggregate contract returned by `/api/dashboard/overview`."""

    total_papers: int
    year_range: YearRange
    publication_trend: list[TrendPoint]
    field_distribution: list[FieldCount]
    top_keywords: list[KeywordCount]
    collaboration_edges: list[CollaborationEdge]
