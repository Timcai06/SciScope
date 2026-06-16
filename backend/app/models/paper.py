from pydantic import BaseModel, Field


class Paper(BaseModel):
    paper_id: str
    title: str
    abstract: str = ""
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    keywords: list[str] = Field(default_factory=list)
    field: str = "unknown"
    full_text: str = ""
