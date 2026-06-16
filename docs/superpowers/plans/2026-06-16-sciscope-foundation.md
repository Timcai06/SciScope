# SciScope Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first working vertical slice of SciScope: project skeleton, data ingestion, basic literature analytics, DeepSeek-backed evidence chat, and a product-grade research dashboard shell.

**Architecture:** Use a monorepo with `backend/` for FastAPI services, `frontend/` for Next.js, `data_pipeline/` for reusable ingestion and analytics code, `configs/` for runtime settings, and `docs/` for delivery documents. The first slice uses local JSON/CSV data, SQLite for lightweight structured storage, FAISS-compatible in-memory vector search through a clean interface, and a DeepSeek provider abstraction so the system can run with either a real API key or a deterministic mock during tests.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, Pandas, NumPy, Scikit-learn, NetworkX, pytest, Next.js, TypeScript, Tailwind CSS, ECharts, TanStack Query, DeepSeek API.

---

## File Structure

Create this structure:

```text
backend/
  app/
    __init__.py
    main.py
    core/
      __init__.py
      config.py
    models/
      __init__.py
      paper.py
      schemas.py
    services/
      __init__.py
      corpus_service.py
      deepseek_provider.py
      evidence_chat.py
      analytics_service.py
    api/
      __init__.py
      routes_dashboard.py
      routes_chat.py
      routes_ingest.py
  tests/
    test_ingest.py
    test_analytics.py
    test_evidence_chat.py
data_pipeline/
  __init__.py
  loaders.py
  normalize.py
  analytics.py
  sample_data.py
frontend/
  package.json
  next.config.mjs
  tsconfig.json
  postcss.config.mjs
  tailwind.config.ts
  app/
    layout.tsx
    page.tsx
    globals.css
  src/
    api/client.ts
    components/
      AppShell.tsx
      DashboardOverview.tsx
      EvidenceChat.tsx
      MetricTile.tsx
      TrendChart.tsx
      KeywordPanel.tsx
    types.ts
configs/
  app.example.env
docs/
  runbook.md
outputs/
  sample/
    papers.sample.json
```

Responsibilities:

- `data_pipeline/`: pure data functions with no web framework dependencies.
- `backend/app/services/`: application services that call data functions and model providers.
- `backend/app/api/`: HTTP route definitions only.
- `frontend/src/components/`: focused UI components for the product shell.
- `outputs/sample/`: deterministic sample data used for local testing and screenshots.

## Task 1: Initialize Repository And Project Skeleton

**Files:**
- Create: `.gitignore`
- Create: `README.md`
- Create: `configs/app.example.env`
- Create directories listed in File Structure.

- [ ] **Step 1: Initialize git repository**

Run:

```bash
git init
```

Expected: command succeeds and creates `.git/`.

- [ ] **Step 2: Create directory tree**

Run:

```bash
mkdir -p backend/app/{core,models,services,api} backend/tests data_pipeline frontend/app frontend/src/{api,components} configs docs outputs/sample
touch backend/app/__init__.py backend/app/core/__init__.py backend/app/models/__init__.py backend/app/services/__init__.py backend/app/api/__init__.py data_pipeline/__init__.py
```

Expected: directories and `__init__.py` files exist.

- [ ] **Step 3: Add ignore rules**

Create `.gitignore`:

```gitignore
.DS_Store
__pycache__/
*.py[cod]
.pytest_cache/
.ruff_cache/
.venv/
venv/
node_modules/
.next/
dist/
build/
.env
*.sqlite
*.db
outputs/generated/
```

- [ ] **Step 4: Add environment example**

Create `configs/app.example.env`:

```dotenv
SCISCOPE_APP_NAME=SciScope
SCISCOPE_ENV=local
SCISCOPE_DATA_PATH=outputs/sample/papers.sample.json
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
SCISCOPE_USE_MOCK_LLM=true
```

- [ ] **Step 5: Add root README**

Create `README.md`:

```markdown
# SciScope

SciScope is a research literature intelligence workspace for scientific paper analysis. It combines literature metadata analytics, evidence-based question answering, DeepSeek-powered reasoning, and product-grade visual exploration.

## First vertical slice

- Import sample paper metadata from JSON or CSV.
- Compute publication, keyword, and author collaboration analytics.
- Serve dashboard and evidence-chat APIs through FastAPI.
- Render a Next.js research workspace with charts and evidence cards.

## Local development

See `docs/runbook.md`.
```

- [ ] **Step 6: Commit skeleton**

Run:

```bash
git add .gitignore README.md configs backend data_pipeline frontend docs outputs
git commit -m "chore: initialize sciscope workspace"
```

Expected: commit succeeds.

## Task 2: Add Deterministic Sample Literature Data

**Files:**
- Create: `outputs/sample/papers.sample.json`
- Create: `data_pipeline/sample_data.py`
- Test: `backend/tests/test_ingest.py`

- [ ] **Step 1: Create sample paper dataset**

Create `outputs/sample/papers.sample.json`:

```json
[
  {
    "paper_id": "P001",
    "title": "Graph Neural Networks for Drug Discovery",
    "abstract": "Graph neural networks model molecular structures and improve virtual screening for drug discovery.",
    "authors": ["Li Wei", "Chen Ming"],
    "year": 2021,
    "keywords": ["graph neural network", "drug discovery", "biomedicine"],
    "field": "biomedicine",
    "full_text": "Graph representation learning supports molecular property prediction."
  },
  {
    "paper_id": "P002",
    "title": "Large Language Models for Knowledge Graph Reasoning",
    "abstract": "Large language models enhance knowledge graph completion and multi-hop reasoning.",
    "authors": ["Zhang Rui", "Li Wei"],
    "year": 2023,
    "keywords": ["large language model", "knowledge graph", "reasoning"],
    "field": "computer science",
    "full_text": "The method combines retrieval augmented generation with graph reasoning."
  },
  {
    "paper_id": "P003",
    "title": "Machine Learning Accelerated Materials Discovery",
    "abstract": "Machine learning methods accelerate material property prediction and candidate screening.",
    "authors": ["Wang Han", "Sun Yue"],
    "year": 2022,
    "keywords": ["machine learning", "materials discovery", "property prediction"],
    "field": "materials science",
    "full_text": "Surrogate models reduce experimental cost in materials design."
  },
  {
    "paper_id": "P004",
    "title": "Retrieval Augmented Generation for Scientific Question Answering",
    "abstract": "Retrieval augmented generation improves scientific question answering by grounding answers in paper evidence.",
    "authors": ["Zhang Rui", "Garcia Ana"],
    "year": 2024,
    "keywords": ["retrieval augmented generation", "scientific qa", "evidence"],
    "field": "computer science",
    "full_text": "Evidence-aware generation reduces hallucination in literature assistants."
  },
  {
    "paper_id": "P005",
    "title": "Transformer Models for Biomedical Literature Mining",
    "abstract": "Transformer models extract biomedical entities and relations from large-scale scientific abstracts.",
    "authors": ["Chen Ming", "Garcia Ana"],
    "year": 2020,
    "keywords": ["transformer", "biomedical literature mining", "entity extraction"],
    "field": "biomedicine",
    "full_text": "Pretrained language models improve biomedical named entity recognition."
  }
]
```

- [ ] **Step 2: Add reusable sample path helper**

Create `data_pipeline/sample_data.py`:

```python
from pathlib import Path


def sample_papers_path() -> Path:
    return Path(__file__).resolve().parents[1] / "outputs" / "sample" / "papers.sample.json"
```

- [ ] **Step 3: Add initial ingest test file**

Create `backend/tests/test_ingest.py`:

```python
from data_pipeline.sample_data import sample_papers_path


def test_sample_data_exists():
    path = sample_papers_path()
    assert path.exists()
    assert path.name == "papers.sample.json"
```

- [ ] **Step 4: Run test**

Run:

```bash
python3 -m pytest backend/tests/test_ingest.py -v
```

Expected: `1 passed`.

- [ ] **Step 5: Commit sample data**

Run:

```bash
git add outputs/sample/papers.sample.json data_pipeline/sample_data.py backend/tests/test_ingest.py
git commit -m "test: add sample literature dataset"
```

Expected: commit succeeds.

## Task 3: Implement Data Loading And Normalization

**Files:**
- Create: `backend/app/models/paper.py`
- Create: `data_pipeline/loaders.py`
- Create: `data_pipeline/normalize.py`
- Modify: `backend/tests/test_ingest.py`

- [ ] **Step 1: Write ingestion tests**

Replace `backend/tests/test_ingest.py`:

```python
from data_pipeline.loaders import load_papers
from data_pipeline.normalize import normalize_keyword, normalize_paper
from data_pipeline.sample_data import sample_papers_path


def test_sample_data_exists():
    path = sample_papers_path()
    assert path.exists()
    assert path.name == "papers.sample.json"


def test_load_papers_from_json():
    papers = load_papers(sample_papers_path())
    assert len(papers) == 5
    assert papers[0]["paper_id"] == "P001"
    assert "graph neural network" in papers[0]["keywords"]


def test_normalize_keyword():
    assert normalize_keyword(" Graph Neural Network ") == "graph neural network"
    assert normalize_keyword("Large-Language Model") == "large language model"


def test_normalize_paper_defaults():
    raw = {
        "paper_id": "X1",
        "title": " Test Title ",
        "abstract": " Test abstract ",
        "authors": "Alice; Bob",
        "year": "2024",
        "keywords": "AI; RAG",
        "field": "",
        "full_text": None,
    }
    paper = normalize_paper(raw)
    assert paper["title"] == "Test Title"
    assert paper["authors"] == ["Alice", "Bob"]
    assert paper["year"] == 2024
    assert paper["keywords"] == ["ai", "rag"]
    assert paper["field"] == "unknown"
    assert paper["full_text"] == ""
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
python3 -m pytest backend/tests/test_ingest.py -v
```

Expected: FAIL because `data_pipeline.loaders` and `data_pipeline.normalize` do not exist.

- [ ] **Step 3: Add paper model**

Create `backend/app/models/paper.py`:

```python
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
```

- [ ] **Step 4: Add normalization utilities**

Create `data_pipeline/normalize.py`:

```python
import re
from typing import Any


def normalize_keyword(value: str) -> str:
    cleaned = value.strip().lower().replace("-", " ")
    return re.sub(r"\s+", " ", cleaned)


def _split_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).replace(",", ";")
    return [part.strip() for part in text.split(";") if part.strip()]


def normalize_paper(raw: dict[str, Any]) -> dict[str, Any]:
    keywords = [normalize_keyword(item) for item in _split_list(raw.get("keywords"))]
    authors = _split_list(raw.get("authors"))
    year_value = raw.get("year")
    year = int(year_value) if str(year_value).strip().isdigit() else None
    field = str(raw.get("field") or "unknown").strip().lower() or "unknown"
    return {
        "paper_id": str(raw.get("paper_id", "")).strip(),
        "title": str(raw.get("title", "")).strip(),
        "abstract": str(raw.get("abstract") or "").strip(),
        "authors": authors,
        "year": year,
        "keywords": keywords,
        "field": field,
        "full_text": str(raw.get("full_text") or "").strip(),
    }
```

- [ ] **Step 5: Add JSON and CSV loader**

Create `data_pipeline/loaders.py`:

```python
import csv
import json
from pathlib import Path
from typing import Any

from data_pipeline.normalize import normalize_paper


def load_papers(path: str | Path) -> list[dict[str, Any]]:
    source = Path(path)
    if source.suffix.lower() == ".json":
        records = json.loads(source.read_text(encoding="utf-8"))
    elif source.suffix.lower() == ".csv":
        with source.open("r", encoding="utf-8", newline="") as handle:
            records = list(csv.DictReader(handle))
    else:
        raise ValueError(f"Unsupported paper data format: {source.suffix}")
    if not isinstance(records, list):
        raise ValueError("Paper data must be a list of records")
    return [normalize_paper(record) for record in records]
```

- [ ] **Step 6: Run tests**

Run:

```bash
python3 -m pytest backend/tests/test_ingest.py -v
```

Expected: `4 passed`.

- [ ] **Step 7: Commit ingestion code**

Run:

```bash
git add backend/app/models/paper.py data_pipeline/loaders.py data_pipeline/normalize.py backend/tests/test_ingest.py
git commit -m "feat: load and normalize paper metadata"
```

Expected: commit succeeds.

## Task 4: Implement Literature Analytics

**Files:**
- Create: `data_pipeline/analytics.py`
- Create: `backend/app/services/analytics_service.py`
- Create: `backend/tests/test_analytics.py`

- [ ] **Step 1: Write analytics tests**

Create `backend/tests/test_analytics.py`:

```python
from data_pipeline.analytics import (
    author_collaboration_edges,
    field_distribution,
    keyword_counts,
    publication_trend,
)
from data_pipeline.loaders import load_papers
from data_pipeline.sample_data import sample_papers_path


def _papers():
    return load_papers(sample_papers_path())


def test_publication_trend():
    trend = publication_trend(_papers())
    assert trend == [
        {"year": 2020, "count": 1},
        {"year": 2021, "count": 1},
        {"year": 2022, "count": 1},
        {"year": 2023, "count": 1},
        {"year": 2024, "count": 1},
    ]


def test_keyword_counts():
    counts = keyword_counts(_papers(), limit=3)
    assert counts[0]["keyword"] in {"graph neural network", "drug discovery", "biomedicine"}
    assert counts[0]["count"] == 1
    assert len(counts) == 3


def test_field_distribution():
    fields = field_distribution(_papers())
    assert fields == [
        {"field": "biomedicine", "count": 2},
        {"field": "computer science", "count": 2},
        {"field": "materials science", "count": 1},
    ]


def test_author_collaboration_edges():
    edges = author_collaboration_edges(_papers())
    assert {"source": "Li Wei", "target": "Chen Ming", "weight": 1} in edges
    assert {"source": "Zhang Rui", "target": "Garcia Ana", "weight": 1} in edges
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
python3 -m pytest backend/tests/test_analytics.py -v
```

Expected: FAIL because `data_pipeline.analytics` does not exist.

- [ ] **Step 3: Implement analytics functions**

Create `data_pipeline/analytics.py`:

```python
from collections import Counter
from itertools import combinations
from typing import Any


def publication_trend(papers: list[dict[str, Any]]) -> list[dict[str, int]]:
    counts = Counter(paper["year"] for paper in papers if paper.get("year") is not None)
    return [{"year": year, "count": counts[year]} for year in sorted(counts)]


def keyword_counts(papers: list[dict[str, Any]], limit: int = 20) -> list[dict[str, int | str]]:
    counts: Counter[str] = Counter()
    for paper in papers:
        counts.update(paper.get("keywords", []))
    return [{"keyword": keyword, "count": count} for keyword, count in counts.most_common(limit)]


def field_distribution(papers: list[dict[str, Any]]) -> list[dict[str, int | str]]:
    counts = Counter(paper.get("field", "unknown") for paper in papers)
    return [{"field": field, "count": count} for field, count in sorted(counts.items())]


def author_collaboration_edges(papers: list[dict[str, Any]]) -> list[dict[str, int | str]]:
    counts: Counter[tuple[str, str]] = Counter()
    for paper in papers:
        authors = sorted(set(paper.get("authors", [])))
        for source, target in combinations(authors, 2):
            counts[(source, target)] += 1
    return [
        {"source": source, "target": target, "weight": weight}
        for (source, target), weight in sorted(counts.items())
    ]
```

- [ ] **Step 4: Add analytics service**

Create `backend/app/services/analytics_service.py`:

```python
from typing import Any

from data_pipeline.analytics import (
    author_collaboration_edges,
    field_distribution,
    keyword_counts,
    publication_trend,
)


def build_dashboard_overview(papers: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total_papers": len(papers),
        "year_range": _year_range(papers),
        "publication_trend": publication_trend(papers),
        "field_distribution": field_distribution(papers),
        "top_keywords": keyword_counts(papers, limit=10),
        "collaboration_edges": author_collaboration_edges(papers),
    }


def _year_range(papers: list[dict[str, Any]]) -> dict[str, int | None]:
    years = [paper["year"] for paper in papers if paper.get("year") is not None]
    if not years:
        return {"start": None, "end": None}
    return {"start": min(years), "end": max(years)}
```

- [ ] **Step 5: Run analytics tests**

Run:

```bash
python3 -m pytest backend/tests/test_analytics.py -v
```

Expected: `4 passed`.

- [ ] **Step 6: Commit analytics**

Run:

```bash
git add data_pipeline/analytics.py backend/app/services/analytics_service.py backend/tests/test_analytics.py
git commit -m "feat: compute literature analytics"
```

Expected: commit succeeds.

## Task 5: Implement Backend Configuration And Corpus Service

**Files:**
- Create: `backend/app/core/config.py`
- Create: `backend/app/services/corpus_service.py`
- Create: `backend/app/models/schemas.py`
- Modify: `backend/tests/test_analytics.py`

- [ ] **Step 1: Extend tests for dashboard overview**

Append to `backend/tests/test_analytics.py`:

```python
from backend.app.services.analytics_service import build_dashboard_overview


def test_build_dashboard_overview():
    overview = build_dashboard_overview(_papers())
    assert overview["total_papers"] == 5
    assert overview["year_range"] == {"start": 2020, "end": 2024}
    assert len(overview["publication_trend"]) == 5
    assert len(overview["top_keywords"]) == 10
```

- [ ] **Step 2: Run test**

Run:

```bash
python3 -m pytest backend/tests/test_analytics.py::test_build_dashboard_overview -v
```

Expected: PASS because service was added in Task 4.

- [ ] **Step 3: Add config model**

Create `backend/app/core/config.py`:

```python
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    app_name: str
    env: str
    data_path: Path
    deepseek_api_key: str
    deepseek_base_url: str
    deepseek_model: str
    use_mock_llm: bool


def get_settings() -> Settings:
    return Settings(
        app_name=os.getenv("SCISCOPE_APP_NAME", "SciScope"),
        env=os.getenv("SCISCOPE_ENV", "local"),
        data_path=Path(os.getenv("SCISCOPE_DATA_PATH", "outputs/sample/papers.sample.json")),
        deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", ""),
        deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        use_mock_llm=os.getenv("SCISCOPE_USE_MOCK_LLM", "true").lower() == "true",
    )
```

- [ ] **Step 4: Add response schemas**

Create `backend/app/models/schemas.py`:

```python
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
```

- [ ] **Step 5: Add corpus service**

Create `backend/app/services/corpus_service.py`:

```python
from functools import lru_cache
from typing import Any

from backend.app.core.config import get_settings
from data_pipeline.loaders import load_papers


@lru_cache(maxsize=1)
def get_corpus() -> list[dict[str, Any]]:
    settings = get_settings()
    return load_papers(settings.data_path)
```

- [ ] **Step 6: Run all backend tests**

Run:

```bash
python3 -m pytest backend/tests -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit config and corpus services**

Run:

```bash
git add backend/app/core/config.py backend/app/models/schemas.py backend/app/services/corpus_service.py backend/tests/test_analytics.py
git commit -m "feat: add backend configuration and corpus service"
```

Expected: commit succeeds.

## Task 6: Implement Evidence Chat With DeepSeek Provider Abstraction

**Files:**
- Create: `backend/app/services/deepseek_provider.py`
- Create: `backend/app/services/evidence_chat.py`
- Create: `backend/tests/test_evidence_chat.py`

- [ ] **Step 1: Write evidence chat tests**

Create `backend/tests/test_evidence_chat.py`:

```python
from backend.app.services.evidence_chat import answer_question
from data_pipeline.loaders import load_papers
from data_pipeline.sample_data import sample_papers_path


def test_answer_question_returns_evidence():
    papers = load_papers(sample_papers_path())
    response = answer_question("What does RAG improve?", papers)
    assert "RAG" in response.answer or "retrieval" in response.answer.lower()
    assert len(response.evidence) >= 1
    assert response.confidence == "medium"


def test_answer_question_matches_keyword_evidence():
    papers = load_papers(sample_papers_path())
    response = answer_question("knowledge graph reasoning", papers)
    titles = [item.title for item in response.evidence]
    assert "Large Language Models for Knowledge Graph Reasoning" in titles
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
python3 -m pytest backend/tests/test_evidence_chat.py -v
```

Expected: FAIL because evidence chat service does not exist.

- [ ] **Step 3: Add DeepSeek provider abstraction**

Create `backend/app/services/deepseek_provider.py`:

```python
from typing import Protocol

from backend.app.core.config import get_settings


class LLMProvider(Protocol):
    def complete(self, prompt: str) -> str:
        ...


class MockDeepSeekProvider:
    def complete(self, prompt: str) -> str:
        return (
            "Based on the retrieved paper evidence, retrieval augmented generation "
            "improves scientific question answering by grounding generated answers "
            "in explicit literature evidence."
        )


class DeepSeekProvider:
    def complete(self, prompt: str) -> str:
        settings = get_settings()
        if not settings.deepseek_api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is required when SCISCOPE_USE_MOCK_LLM=false")
        raise RuntimeError("Real DeepSeek HTTP call is implemented in the API integration task")


def get_llm_provider() -> LLMProvider:
    settings = get_settings()
    if settings.use_mock_llm:
        return MockDeepSeekProvider()
    return DeepSeekProvider()
```

- [ ] **Step 4: Add evidence chat service**

Create `backend/app/services/evidence_chat.py`:

```python
from typing import Any

from backend.app.models.schemas import ChatResponse, EvidenceItem
from backend.app.services.deepseek_provider import get_llm_provider


def answer_question(question: str, papers: list[dict[str, Any]]) -> ChatResponse:
    evidence = _retrieve_evidence(question, papers)
    prompt = _build_prompt(question, evidence)
    answer = get_llm_provider().complete(prompt)
    return ChatResponse(answer=answer, evidence=evidence, confidence="medium")


def _retrieve_evidence(question: str, papers: list[dict[str, Any]], limit: int = 3) -> list[EvidenceItem]:
    query_terms = {token.lower() for token in question.replace("-", " ").split() if len(token) > 2}
    scored: list[tuple[int, dict[str, Any]]] = []
    for paper in papers:
        haystack = " ".join(
            [
                paper.get("title", ""),
                paper.get("abstract", ""),
                " ".join(paper.get("keywords", [])),
                paper.get("full_text", ""),
            ]
        ).lower()
        score = sum(1 for term in query_terms if term in haystack)
        if score > 0:
            scored.append((score, paper))
    ranked = [paper for _, paper in sorted(scored, key=lambda item: item[0], reverse=True)[:limit]]
    return [
        EvidenceItem(
            paper_id=paper["paper_id"],
            title=paper["title"],
            year=paper.get("year"),
            reason="Matched query terms in title, abstract, keywords, or full text.",
        )
        for paper in ranked
    ]


def _build_prompt(question: str, evidence: list[EvidenceItem]) -> str:
    evidence_lines = "\n".join(
        f"- {item.paper_id} | {item.title} | {item.year} | {item.reason}" for item in evidence
    )
    return (
        "You are SciScope, an evidence-based scientific literature analyst.\n"
        f"Question: {question}\n"
        f"Evidence:\n{evidence_lines}\n"
        "Answer in Chinese with a concise conclusion and mention that the answer is grounded in retrieved evidence."
    )
```

- [ ] **Step 5: Run evidence chat tests**

Run:

```bash
python3 -m pytest backend/tests/test_evidence_chat.py -v
```

Expected: `2 passed`.

- [ ] **Step 6: Commit evidence chat**

Run:

```bash
git add backend/app/services/deepseek_provider.py backend/app/services/evidence_chat.py backend/tests/test_evidence_chat.py
git commit -m "feat: add evidence-based DeepSeek chat abstraction"
```

Expected: commit succeeds.

## Task 7: Implement FastAPI Routes

**Files:**
- Create: `backend/app/api/routes_dashboard.py`
- Create: `backend/app/api/routes_chat.py`
- Create: `backend/app/api/routes_ingest.py`
- Create: `backend/app/main.py`

- [ ] **Step 1: Add dashboard route**

Create `backend/app/api/routes_dashboard.py`:

```python
from fastapi import APIRouter

from backend.app.models.schemas import DashboardResponse
from backend.app.services.analytics_service import build_dashboard_overview
from backend.app.services.corpus_service import get_corpus

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/overview", response_model=DashboardResponse)
def dashboard_overview() -> DashboardResponse:
    return DashboardResponse(**build_dashboard_overview(get_corpus()))
```

- [ ] **Step 2: Add chat route**

Create `backend/app/api/routes_chat.py`:

```python
from fastapi import APIRouter

from backend.app.models.schemas import ChatRequest, ChatResponse
from backend.app.services.corpus_service import get_corpus
from backend.app.services.evidence_chat import answer_question

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    return answer_question(request.question, get_corpus())
```

- [ ] **Step 3: Add ingest route**

Create `backend/app/api/routes_ingest.py`:

```python
from fastapi import APIRouter

from backend.app.services.corpus_service import get_corpus

router = APIRouter(prefix="/api/ingest", tags=["ingest"])


@router.get("/status")
def ingest_status() -> dict[str, int | str]:
    corpus = get_corpus()
    return {"status": "ready", "papers": len(corpus)}
```

- [ ] **Step 4: Add FastAPI app**

Create `backend/app/main.py`:

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.routes_chat import router as chat_router
from backend.app.api.routes_dashboard import router as dashboard_router
from backend.app.api.routes_ingest import router as ingest_router
from backend.app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(dashboard_router)
    app.include_router(chat_router)
    app.include_router(ingest_router)
    return app


app = create_app()
```

- [ ] **Step 5: Run backend test suite**

Run:

```bash
python3 -m pytest backend/tests -v
```

Expected: all tests pass.

- [ ] **Step 6: Smoke test API app import**

Run:

```bash
python3 -c "from backend.app.main import app; print(app.title)"
```

Expected output:

```text
SciScope
```

- [ ] **Step 7: Commit API routes**

Run:

```bash
git add backend/app/api backend/app/main.py
git commit -m "feat: expose sciscope backend api"
```

Expected: commit succeeds.

## Task 8: Scaffold Product-Grade Next.js Frontend

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/next.config.mjs`
- Create: `frontend/tsconfig.json`
- Create: `frontend/postcss.config.mjs`
- Create: `frontend/tailwind.config.ts`
- Create: `frontend/app/layout.tsx`
- Create: `frontend/app/globals.css`
- Create: `frontend/src/types.ts`
- Create: `frontend/src/api/client.ts`

- [ ] **Step 1: Add package metadata**

Create `frontend/package.json`:

```json
{
  "name": "sciscope-frontend",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "lint": "next lint"
  },
  "dependencies": {
    "@tanstack/react-query": "^5.80.7",
    "echarts": "^5.6.0",
    "framer-motion": "^12.18.1",
    "next": "^15.3.3",
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "zod": "^3.25.64",
    "zustand": "^5.0.5"
  },
  "devDependencies": {
    "@types/node": "^22.15.31",
    "@types/react": "^19.0.12",
    "@types/react-dom": "^19.0.4",
    "autoprefixer": "^10.4.21",
    "postcss": "^8.5.4",
    "tailwindcss": "^3.4.17",
    "typescript": "^5.8.3"
  }
}
```

- [ ] **Step 2: Add Next.js config**

Create `frontend/next.config.mjs`:

```javascript
const nextConfig = {
  reactStrictMode: true
};

export default nextConfig;
```

- [ ] **Step 3: Add TypeScript config**

Create `frontend/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": false,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "paths": {
      "@/*": ["./src/*"]
    }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx"],
  "exclude": ["node_modules"]
}
```

- [ ] **Step 4: Add Tailwind config**

Create `frontend/postcss.config.mjs`:

```javascript
const config = {
  plugins: {
    tailwindcss: {},
    autoprefixer: {}
  }
};

export default config;
```

Create `frontend/tailwind.config.ts`:

```typescript
import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        graphite: "#121417",
        panel: "#191d22",
        line: "#2a3038",
        signal: "#e65045",
        cyanSoft: "#6bd6d6",
        silver: "#d7dde5"
      }
    }
  },
  plugins: []
};

export default config;
```

- [ ] **Step 5: Add app layout and global styles**

Create `frontend/app/layout.tsx`:

```tsx
import "./globals.css";
import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "SciScope",
  description: "Research literature intelligence workspace"
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
```

Create `frontend/app/globals.css`:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  color-scheme: dark;
  background: #121417;
  color: #d7dde5;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  min-height: 100vh;
  background: #121417;
  font-family: Arial, Helvetica, sans-serif;
}
```

- [ ] **Step 6: Add frontend types**

Create `frontend/src/types.ts`:

```typescript
export type TrendPoint = {
  year: number;
  count: number;
};

export type KeywordCount = {
  keyword: string;
  count: number;
};

export type FieldCount = {
  field: string;
  count: number;
};

export type CollaborationEdge = {
  source: string;
  target: string;
  weight: number;
};

export type DashboardOverview = {
  total_papers: number;
  year_range: {
    start: number | null;
    end: number | null;
  };
  publication_trend: TrendPoint[];
  field_distribution: FieldCount[];
  top_keywords: KeywordCount[];
  collaboration_edges: CollaborationEdge[];
};

export type EvidenceItem = {
  paper_id: string;
  title: string;
  year: number | null;
  reason: string;
};

export type ChatResponse = {
  answer: string;
  evidence: EvidenceItem[];
  confidence: string;
};
```

- [ ] **Step 7: Add API client**

Create `frontend/src/api/client.ts`:

```typescript
import type { ChatResponse, DashboardOverview } from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_SCISCOPE_API_BASE ?? "http://localhost:8000";

export async function fetchDashboardOverview(): Promise<DashboardOverview> {
  const response = await fetch(`${API_BASE}/api/dashboard/overview`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error("Failed to load dashboard overview");
  }
  return response.json();
}

export async function askQuestion(question: string): Promise<ChatResponse> {
  const response = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question })
  });
  if (!response.ok) {
    throw new Error("Failed to ask SciScope");
  }
  return response.json();
}
```

- [ ] **Step 8: Install frontend dependencies**

Run:

```bash
cd frontend && npm install
```

Expected: dependencies install and `package-lock.json` is created.

- [ ] **Step 9: Commit frontend scaffold**

Run:

```bash
git add frontend
git commit -m "feat: scaffold sciscope frontend"
```

Expected: commit succeeds.

## Task 9: Build Dashboard UI Components

**Files:**
- Create: `frontend/src/components/MetricTile.tsx`
- Create: `frontend/src/components/TrendChart.tsx`
- Create: `frontend/src/components/KeywordPanel.tsx`
- Create: `frontend/src/components/DashboardOverview.tsx`
- Create: `frontend/src/components/AppShell.tsx`
- Create: `frontend/app/page.tsx`

- [ ] **Step 1: Add metric tile**

Create `frontend/src/components/MetricTile.tsx`:

```tsx
type MetricTileProps = {
  label: string;
  value: string;
  accent?: string;
};

export function MetricTile({ label, value, accent = "text-cyanSoft" }: MetricTileProps) {
  return (
    <section className="border border-line bg-panel p-4">
      <p className="text-xs uppercase tracking-widest text-silver/60">{label}</p>
      <p className={`mt-3 text-3xl font-semibold ${accent}`}>{value}</p>
    </section>
  );
}
```

- [ ] **Step 2: Add lightweight trend bar chart component**

Create `frontend/src/components/TrendChart.tsx`:

```tsx
import type { TrendPoint } from "@/types";

export function TrendChart({ data }: { data: TrendPoint[] }) {
  const max = Math.max(...data.map((item) => item.count), 1);
  return (
    <section className="border border-line bg-panel p-4">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-silver">Publication Trend</h2>
        <span className="text-xs text-silver/50">Temporal Rail</span>
      </div>
      <div className="flex h-48 items-end gap-3">
        {data.map((item) => (
          <div className="flex flex-1 flex-col items-center gap-2" key={item.year}>
            <div
              className="w-full bg-cyanSoft"
              style={{ height: `${Math.max((item.count / max) * 100, 8)}%` }}
              title={`${item.year}: ${item.count}`}
            />
            <span className="text-xs text-silver/60">{item.year}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
```

- [ ] **Step 3: Add keyword panel**

Create `frontend/src/components/KeywordPanel.tsx`:

```tsx
import type { KeywordCount } from "@/types";

export function KeywordPanel({ keywords }: { keywords: KeywordCount[] }) {
  return (
    <section className="border border-line bg-panel p-4">
      <h2 className="text-sm font-semibold text-silver">Rising Signals</h2>
      <div className="mt-4 flex flex-wrap gap-2">
        {keywords.map((item) => (
          <span className="border border-line px-3 py-2 text-xs text-silver" key={item.keyword}>
            {item.keyword}
            <span className="ml-2 text-cyanSoft">{item.count}</span>
          </span>
        ))}
      </div>
    </section>
  );
}
```

- [ ] **Step 4: Add dashboard overview**

Create `frontend/src/components/DashboardOverview.tsx`:

```tsx
import type { DashboardOverview as DashboardOverviewType } from "@/types";
import { KeywordPanel } from "./KeywordPanel";
import { MetricTile } from "./MetricTile";
import { TrendChart } from "./TrendChart";

export function DashboardOverview({ overview }: { overview: DashboardOverviewType }) {
  const yearRange =
    overview.year_range.start && overview.year_range.end
      ? `${overview.year_range.start}-${overview.year_range.end}`
      : "Unknown";

  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_360px]">
      <div className="space-y-4">
        <div className="grid gap-4 md:grid-cols-3">
          <MetricTile label="Papers" value={String(overview.total_papers)} />
          <MetricTile label="Years" value={yearRange} accent="text-silver" />
          <MetricTile label="Collaborations" value={String(overview.collaboration_edges.length)} accent="text-signal" />
        </div>
        <TrendChart data={overview.publication_trend} />
      </div>
      <div className="space-y-4">
        <KeywordPanel keywords={overview.top_keywords} />
        <section className="border border-line bg-panel p-4">
          <h2 className="text-sm font-semibold text-silver">Field Distribution</h2>
          <div className="mt-4 space-y-3">
            {overview.field_distribution.map((item) => (
              <div className="flex items-center justify-between text-sm" key={item.field}>
                <span className="text-silver/70">{item.field}</span>
                <span className="text-cyanSoft">{item.count}</span>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Add app shell**

Create `frontend/src/components/AppShell.tsx`:

```tsx
import type { ReactNode } from "react";

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <main className="min-h-screen bg-graphite text-silver">
      <div className="grid min-h-screen lg:grid-cols-[260px_1fr]">
        <aside className="border-r border-line bg-[#15181d] p-5">
          <div className="text-lg font-semibold">SciScope</div>
          <p className="mt-2 text-xs leading-5 text-silver/50">Research literature intelligence workspace</p>
          <nav className="mt-8 space-y-2 text-sm">
            {["Research Radar", "Evidence Chat", "Knowledge Galaxy", "Collaboration Map", "Report Studio"].map((item) => (
              <div className="border border-line px-3 py-2 text-silver/70" key={item}>
                {item}
              </div>
            ))}
          </nav>
        </aside>
        <section className="p-5 lg:p-8">
          <header className="mb-6 flex items-end justify-between border-b border-line pb-5">
            <div>
              <p className="text-xs uppercase tracking-widest text-cyanSoft">Research Command Center</p>
              <h1 className="mt-2 text-3xl font-semibold text-silver">科研文献洞察工作台</h1>
            </div>
            <div className="text-right text-xs text-silver/50">
              DeepSeek-ready
              <br />
              Evidence-first
            </div>
          </header>
          {children}
        </section>
      </div>
    </main>
  );
}
```

- [ ] **Step 6: Add dashboard page**

Create `frontend/app/page.tsx`:

```tsx
import { fetchDashboardOverview } from "@/api/client";
import { AppShell } from "@/components/AppShell";
import { DashboardOverview } from "@/components/DashboardOverview";

export default async function HomePage() {
  const overview = await fetchDashboardOverview();
  return (
    <AppShell>
      <DashboardOverview overview={overview} />
    </AppShell>
  );
}
```

- [ ] **Step 7: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: build succeeds when backend is running or when API calls are mocked. If build fails because the backend is not running during server rendering, replace the page with a client component in Task 10.

- [ ] **Step 8: Commit dashboard UI**

Run:

```bash
git add frontend/app frontend/src
git commit -m "feat: build research dashboard shell"
```

Expected: commit succeeds.

## Task 10: Add Evidence Chat UI

**Files:**
- Create: `frontend/src/components/EvidenceChat.tsx`
- Modify: `frontend/app/page.tsx`

- [ ] **Step 1: Add client chat component**

Create `frontend/src/components/EvidenceChat.tsx`:

```tsx
"use client";

import { useState } from "react";
import { askQuestion } from "@/api/client";
import type { ChatResponse } from "@/types";

export function EvidenceChat() {
  const [question, setQuestion] = useState("knowledge graph reasoning");
  const [response, setResponse] = useState<ChatResponse | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit() {
    setLoading(true);
    try {
      setResponse(await askQuestion(question));
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="mt-4 border border-line bg-panel p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-silver">Evidence Chat</h2>
        <span className="text-xs text-cyanSoft">DeepSeek Agent</span>
      </div>
      <div className="mt-4 flex gap-3">
        <input
          className="min-w-0 flex-1 border border-line bg-graphite px-3 py-2 text-sm text-silver outline-none"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
        />
        <button className="border border-cyanSoft px-4 py-2 text-sm text-cyanSoft" onClick={submit} disabled={loading}>
          {loading ? "Thinking" : "Ask"}
        </button>
      </div>
      {response ? (
        <div className="mt-4 grid gap-4 lg:grid-cols-[1fr_360px]">
          <div className="border border-line bg-graphite p-4 text-sm leading-6 text-silver/80">{response.answer}</div>
          <div className="space-y-3">
            {response.evidence.map((item) => (
              <article className="border border-line bg-graphite p-3" key={item.paper_id}>
                <div className="text-xs text-cyanSoft">{item.paper_id} · {item.year ?? "unknown"}</div>
                <div className="mt-1 text-sm text-silver">{item.title}</div>
                <p className="mt-2 text-xs leading-5 text-silver/50">{item.reason}</p>
              </article>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}
```

- [ ] **Step 2: Add chat to page**

Modify `frontend/app/page.tsx`:

```tsx
import { fetchDashboardOverview } from "@/api/client";
import { AppShell } from "@/components/AppShell";
import { DashboardOverview } from "@/components/DashboardOverview";
import { EvidenceChat } from "@/components/EvidenceChat";

export default async function HomePage() {
  const overview = await fetchDashboardOverview();
  return (
    <AppShell>
      <DashboardOverview overview={overview} />
      <EvidenceChat />
    </AppShell>
  );
}
```

- [ ] **Step 3: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: build succeeds.

- [ ] **Step 4: Commit chat UI**

Run:

```bash
git add frontend/app/page.tsx frontend/src/components/EvidenceChat.tsx
git commit -m "feat: add evidence chat interface"
```

Expected: commit succeeds.

## Task 11: Add Runbook And Local Verification

**Files:**
- Create: `docs/runbook.md`

- [ ] **Step 1: Write runbook**

Create `docs/runbook.md`:

```markdown
# SciScope Runbook

## Requirements

- Python 3.11+
- Node.js 20+
- npm

## Backend setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install fastapi uvicorn pydantic pandas numpy scikit-learn networkx pytest
export SCISCOPE_DATA_PATH=outputs/sample/papers.sample.json
export SCISCOPE_USE_MOCK_LLM=true
uvicorn backend.app.main:app --reload --port 8000
```

## Backend checks

```bash
python3 -m pytest backend/tests -v
curl http://127.0.0.1:8000/api/ingest/status
curl http://127.0.0.1:8000/api/dashboard/overview
```

## Frontend setup

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`.

## DeepSeek configuration

For local deterministic testing, keep:

```bash
export SCISCOPE_USE_MOCK_LLM=true
```

For real DeepSeek calls, set:

```bash
export SCISCOPE_USE_MOCK_LLM=false
export DEEPSEEK_API_KEY=your_api_key
export DEEPSEEK_MODEL=deepseek-chat
```

The first foundation slice includes the provider boundary and mock provider. Real HTTP integration is implemented after the product shell and evidence contract are stable.
```

- [ ] **Step 2: Run backend tests**

Run:

```bash
python3 -m pytest backend/tests -v
```

Expected: all tests pass.

- [ ] **Step 3: Start backend**

Run:

```bash
uvicorn backend.app.main:app --reload --port 8000
```

Expected: backend starts and serves `http://127.0.0.1:8000/docs`.

- [ ] **Step 4: Start frontend**

Run:

```bash
cd frontend && npm run dev
```

Expected: frontend starts and serves `http://localhost:3000`.

- [ ] **Step 5: Commit runbook**

Run:

```bash
git add docs/runbook.md
git commit -m "docs: add sciscope runbook"
```

Expected: commit succeeds.

## Task 12: Foundation Acceptance Review

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README with acceptance checklist**

Replace `README.md`:

```markdown
# SciScope

SciScope is a research literature intelligence workspace for scientific paper analysis. It combines literature metadata analytics, evidence-based question answering, DeepSeek-powered reasoning, and product-grade visual exploration.

## Foundation slice

This repository currently provides:

- Sample paper metadata under `outputs/sample/papers.sample.json`.
- Data loading and normalization utilities under `data_pipeline/`.
- Literature analytics for publication trends, keyword counts, field distribution, and author collaboration edges.
- FastAPI backend routes for ingest status, dashboard overview, and evidence chat.
- DeepSeek provider boundary with deterministic mock mode.
- Next.js research dashboard shell with metrics, trend view, keyword panel, and evidence chat.

## Local development

See `docs/runbook.md`.

## Acceptance checks

```bash
python3 -m pytest backend/tests -v
uvicorn backend.app.main:app --reload --port 8000
cd frontend && npm run build
```
```

- [ ] **Step 2: Run final backend test**

Run:

```bash
python3 -m pytest backend/tests -v
```

Expected: all tests pass.

- [ ] **Step 3: Run final frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: build succeeds.

- [ ] **Step 4: Commit acceptance update**

Run:

```bash
git add README.md
git commit -m "docs: document foundation acceptance checks"
```

Expected: commit succeeds.

## Scope Deliberately Deferred To Next Plans

These are not part of the foundation slice:

- Real DeepSeek HTTP integration with streaming responses.
- Embedding model selection and vector database persistence.
- Neo4j knowledge graph ingestion.
- GraphRAG path retrieval.
- BERTopic dynamic topic modeling.
- Opportunity Score implementation.
- Report Studio export to PDF or DOCX.
- Full visual Knowledge Galaxy.

They become separate implementation plans after this foundation slice is running end to end.

## Self-Review

- Spec coverage: This plan covers the first executable vertical slice of the product architecture: data ingestion, analytics, backend API, DeepSeek provider boundary, evidence chat, and product-grade frontend shell.
- Product boundary: The full architecture is intentionally split because the approved spec covers several independent subsystems. This plan creates a stable foundation for later GraphRAG, knowledge graph, topic modeling, opportunity generation, and report export plans.
- Placeholder scan: The plan contains concrete files, code blocks, commands, and expected results for every task.
- Type consistency: Backend response models match frontend TypeScript types; route paths match frontend client calls.
