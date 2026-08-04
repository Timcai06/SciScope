from pydantic import BaseModel, Field


class Paper(BaseModel):
    """Canonical normalized paper payload consumed by analysis + infra loaders."""
    paper_id: str
    title: str
    # Keep fields defaulted here to reduce downstream null-handling divergence.
    abstract: str = ""
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    keywords: list[str] = Field(default_factory=list)
    field: str = "unknown"
    full_text: str = ""
