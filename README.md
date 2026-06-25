# SciScope

SciScope is a research literature intelligence workspace for scientific paper
analysis. The foundation slice turns the project brief and sample corpus into a
working local product path: load paper metadata, normalize it, compute research
analytics, expose FastAPI endpoints, and inspect evidence-grounded answers in a
Next.js dashboard.

## Current Foundation Slice

- Source documents: the original project inputs live at
  `docs/competition/赛题.docx` and `docs/competition/数据集.docx`.
- Sample paper metadata: deterministic local paper records are stored in
  `data/sample/papers.sample.json`.
- Project layout: `data/` stores paper data assets, while `output/` stores
  generated charts and final PDFs. See `docs/project_structure.md`.
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
  deterministic mock provider for local verification or an OpenAI-compatible
  local model provider for vLLM/LM Studio.
- Next.js dashboard shell: the frontend renders a SciScope command-center
  layout with metrics, charts, keyword panels, and evidence chat.
- Evidence chat UI: the frontend lets users ask the indexed corpus questions
  and review returned answers, confidence, and cited paper evidence.

## Local Development

Use `docs/runbook.md` for setup, environment variables, backend/frontend start
commands, API smoke checks, and the current webpack workaround for this
repository path.

The shortest local path is:

```bash
make install
make dev
```

Then open `http://localhost:3000`. The backend API docs are available at
`http://127.0.0.1:8000/docs`.

To use a local vLLM-Metal server instead of the mock provider, start vLLM on
`127.0.0.1:8001`, then run:

```bash
make dev-vllm
```

## Terminal agent client (Go) & distribution

The agent UI is a Go / Bubble Tea terminal client (`tui/`) that streams the agent
over SSE. Run it with the backend (`:8000`) and local LLM (`:8001`) up:

```bash
make backend      # terminal 1
make llm          # terminal 2
make tui          # terminal 3  (or point at a remote backend: SCISCOPE_BACKEND=https://host)
```

- **Icons**: tool rows use Nerd Font glyphs. Install one and set it as your
  terminal font: `brew install --cask font-hack-nerd-font`. No Nerd Font?
  run `SCISCOPE_TUI_ICONS=off make tui` for plain text.

**Homebrew distribution** (productization): tag a release and GoReleaser
(`tui/.goreleaser.yaml` + `.github/workflows/release.yml`) builds multi-platform
binaries and publishes a Homebrew cask:

```bash
git tag v0.1.0 && git push origin v0.1.0      # CI cuts the release
brew install Timcai06/sciscope/sciscope-tui    # users install the client
```

One-time setup: create an empty `Timcai06/homebrew-sciscope` repo and add a
`HOMEBREW_TAP_GITHUB_TOKEN` secret (token with write access to that tap repo).

## Acceptance Checks

Run these commands before handing off the foundation slice:

```bash
make test
```

## Current Limitation

The foundation slice supports mock mode and OpenAI-compatible local model
servers such as vLLM-Metal. Real DeepSeek HTTP integration, including
authenticated remote model calls, is deferred to a later implementation slice.
