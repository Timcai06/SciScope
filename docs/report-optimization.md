# Report Optimization Guide

This guide keeps the project report, data report, screenshots, and demo script
aligned with the current product reality after the v0.2.1 hosted release.

## Current Truth Scope

- Packaged TUI users install with Homebrew or Scoop and connect to the hosted
  backend by default.
- The hosted demo backend runs on Render and reads Supabase Postgres/pgvector.
- The hosted free/small instance uses `SCISCOPE_ENABLE_RUNTIME_EMBEDDINGS=false`,
  so public search/chat use PostgreSQL full-text evidence retrieval plus
  DeepSeek generation.
- Local development keeps the heavier full-corpus path: local PostgreSQL,
  chunk embeddings, recommendation vectors, graph assets, evaluation, and PDF
  report generation.
- Current hosted demo data is a small representative subset, not the full local
  corpus.

Do not describe the hosted demo as full-scale semantic production until runtime
query embeddings are enabled on a larger instance and verified.

## Narrative Priority

1. **Productization**: a user can install `sciscope-tui` and ask questions
   without starting a local backend.
2. **Evidence discipline**: answers return evidence rows, confidence, and graph
   expansion context instead of free-form unsupported claims.
3. **Two-tier architecture**: hosted demo is stable and lightweight; local dev is
   the full research lab for corpus rebuilds and semantic retrieval.
4. **Distribution**: Homebrew and Scoop are part of the product delivery, not an
   afterthought.
5. **Upgrade path**: Supabase/Render can move from demo subset to larger managed
   capacity without changing the TUI protocol.

## Screenshots To Add Or Refresh

- TUI default startup connected to hosted backend.
- `sciscope-tui doctor` showing hosted backend `ok`.
- A real `/api/chat` answer with answer, evidence titles, confidence, and graph
  entities.
- Homebrew install or `sciscope-tui --version` output for macOS.
- Scoop install or `sciscope-tui --version` output for Windows.
- Render `/readyz` or API smoke result showing DB/retrieval/model configured.
- Supabase table counts for the hosted demo subset.

Keep screenshots focused and readable. Prefer terminal captures with enough
context to show the command, result, and version, not full desktop screenshots.

## Report Edits

### Project Report

- Add the hosted deployment as a product milestone in the solution section.
- Explain the two-tier environment in the reproducibility section:
  `hosted demo` versus `local full pipeline`.
- Mention Brew/Scoop as cross-platform delivery evidence.
- Keep limitations explicit: hosted demo subset and lexical retrieval on small
  Render instances.

### Data Report

- Keep data-count scopes separate:
  local processed corpus, PostgreSQL subset, evaluation sample, and hosted demo
  subset are different truth scopes.
- Do not merge local full-corpus counts with hosted demo counts into one total.
- If adding hosted screenshots, label them as demo-deployment validation, not as
  full data coverage evidence.

### Design Report

- Show the deployment boundary:
  TUI -> Render FastAPI -> Supabase/pgvector -> DeepSeek.
- Show the local development boundary:
  TUI -> local FastAPI -> local PostgreSQL -> local embedder/vLLM.
- Note that the SSE/API contract lets both environments share the same client.

## Language To Prefer

- "hosted demo backend" instead of "full production corpus" for the current
  Render/Supabase service.
- "public install path" instead of "packaging experiment".
- "runtime semantic retrieval is disabled on the free hosted instance" instead
  of "semantic retrieval is unavailable".
- "local full pipeline remains available" instead of "hosted is reduced".

## Pre-Submission Checks

```bash
SCISCOPE_HOSTED_BACKEND_URL=https://sciscope-backend.onrender.com make hosted-release-preflight
make test-backend
cd tui && go test ./...
make project-report-pdf
make data-report-pdf
```

Before final export, verify that report text does not claim all hosted answers
come from the full local corpus or runtime semantic query embeddings.
