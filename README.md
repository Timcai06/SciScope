# SciScope

SciScope is a research literature intelligence workspace for scientific paper
analysis. The foundation slice turns the project brief and sample corpus into a
working local product path: load paper metadata, normalize it, compute research
analytics, expose FastAPI endpoints, and inspect evidence-grounded answers in a
Next.js dashboard.

## Current Foundation Slice

- Source documents: the original project inputs live at the repository root as
  `赛题.docx` and `数据集.docx`.
- Sample paper metadata: deterministic local paper records are stored in
  `outputs/sample/papers.sample.json`.
- Data loading and normalization: `data_pipeline/` loads JSON or CSV paper
  metadata and normalizes paper IDs, titles, abstracts, authors, years,
  keywords, fields, and full text into shared models.
- Analytics: the backend builds publication trends, field distribution,
  keyword rankings, summary metrics, and author collaboration edges from the
  normalized corpus.
- FastAPI routes: the backend serves ingest status, dashboard analytics, and
  evidence chat through `/api/ingest/status`, `/api/dashboard/overview`, and
  `/api/chat`.
- Evidence-grounded mock DeepSeek chat: the chat service retrieves relevant
  sample papers, returns answer text with evidence cards, and uses a
  deterministic mock DeepSeek provider for local verification.
- Next.js dashboard shell: the frontend renders a SciScope command-center
  layout with metrics, charts, keyword panels, and corpus status.
- Evidence chat UI: the frontend lets users ask the indexed corpus questions
  and review returned answers, confidence, and cited paper evidence.

## Local Development

Use `docs/runbook.md` for setup, environment variables, backend/frontend start
commands, API smoke checks, and the current webpack workaround for this
repository path.

## Acceptance Checks

Run these commands before handing off the foundation slice:

```bash
python3 -m pytest backend/tests -v
cd frontend && npm run typecheck
cd frontend && npm run build
```

## Current Limitation

The foundation slice intentionally uses the mock DeepSeek provider. Real
DeepSeek HTTP integration, including authenticated remote model calls, is
deferred to a later implementation slice.
