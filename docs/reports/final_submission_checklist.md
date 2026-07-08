# SciScope Final Submission Checklist

This checklist is the handoff surface for the final report-polish pass. It keeps
the work focused on presentation, consistency, and judging clarity.

Last reviewed: 2026-07-08.

## Scope Lock

- [x] Do not add data sources, agent tools, frontend scope, release packaging, or
  broad refactors.
- [x] Treat the lower layers as frozen: data, RAG, agent, model assets, and
  architecture are already saturated for this submission.
- [x] Spend the final effort on narrative amplification, format polish, and
  numeric consistency.

## Numeric Truth Sources

- [x] Data analysis report uses `data/analysis/summary.json` and
  `output/assets/sciscope_data_report/data_layer_readiness.json`.
- [x] Processed corpus file uses `data/processed/papers_corpus.summary.json`.
- [x] RAG chunk file uses `data/processed/paper_chunks.summary.json`.
- [x] Runtime service/index counts use PostgreSQL table counts.
- [x] Evaluation metrics use `output/eval/eval_report.json`.

## Current Canonical Metrics

- Raw records: 169,324.
- Analysis records: 168,447.
- Main 2022-2026 analysis-window records: 159,382.
- Processed corpus file records: 159,164.
- Runtime PostgreSQL papers: 159,187.
- Runtime RAG chunks: 367,773.
- Runtime chunk embeddings: 367,773.
- Runtime paper embeddings: 159,135.
- Abstract coverage: 140,183 records, 83.22%.
- Full-text field coverage: 17,682 records, 10.50%.
- RAG full-text chunks: 48,572 chunks covering 13,400 papers.
- Title self-retrieval: recall@10 0.985, MRR@10 0.9583.
- Cross-lingual relevance@5: 1.0.
- Trend backtest Pearson: 0.9756.
- Recommendation mean semantic similarity: 0.8918.
- Backend automated tests: `make test-backend` currently reports 141 passed.
- Live agent smoke: `make agent-smoke` currently passes for corpus size,
  capability boundary, claim-check, trend-analysis, and paper-recommendation
  skill workflows.

## Package Contents Beyond The Two Reports

Use a whitelist package, not a whole-repository dump. Removed historical plan
archives and agent execution traces should not be reconstructed for submission
unless they are deliberately refreshed into current docs.

- [ ] Judge index and run instructions:
  `交付说明.md`, `README.md`, `docs/operations/runbook.md`,
  `docs/release/README.md`, `docs/reports/final_submission_checklist.md`,
  `docs/reports/submission_manifest.md`.
- [ ] Competition source files:
  `docs/competition/赛题.docx`, `docs/competition/数据集.docx`.
- [ ] Python code and runtime schema:
  `src/`, `backend/`, `data_pipeline/`, `infra/`, `configs/`, `Makefile`.
- [ ] Agent skill workflows and live smoke:
  `.sciscope/skills/`, `scripts/agent_smoke.py`.
- [ ] Terminal client:
  `tui/`.
- [ ] Model and index assets that are small enough to ship:
  `models/trends/`, `models/recommend/`, `output/graphs/`, `output/eval/`.
- [ ] Data assets needed for reproducibility:
  `data/raw_canonical/`, `data/analysis/`, `data/processed/`.
- [ ] Report figures and manifests:
  `output/assets/sciscope_data_report/`,
  `output/assets/sciscope_project_report/`.
- [ ] Agent demonstration:
  `docs/examples/golden_verify_claim_session.md` and, if generated before final
  packaging, the latest real `sciscope-session-*.md` export.
- [ ] Large replaceable dependencies decision:
  explicitly include or document rebuild/download steps for
  `models/embedder_local/`, `models/llm_local/`, and PostgreSQL runtime tables.
- [ ] Build the whitelist package with `make submission-package`; inspect
  `output/submission/SciScope_submission_manifest.csv` before upload.
- [ ] Exclude from the formal submission package unless deliberately refreshed:
  `docs/architecture/2026-06-16-sciscope-product-architecture.md` and
  `output/pdf/sciscope_design/`. The old `plan/archive/` and
  `docs/superpowers/` areas have already been removed from the active repo.

## Report Polish Gates

- [x] Delivery note, project report, and data report distinguish analysis,
  processed-corpus, runtime, and evaluation metric scopes.
- [x] Project report opens the results chapter with a visible metric box.
- [x] Project report includes a differentiated capability comparison matrix.
- [x] Project report includes a real `verify_claim` example.
- [x] Data report summary closes the social, economic, and technical innovation
  loop.
- [x] Data report and project report use aligned social/economic value framing.
- [x] Format checklist is filled, not left as an abstract recommendation list.
